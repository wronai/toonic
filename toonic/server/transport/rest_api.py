"""
REST API + WebSocket transport — FastAPI-based server with web UI.

REFACTORED: HTML templates moved to transport/templates/.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("toonic.transport.rest")

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _load_template(name: str) -> str:
    """Load HTML template from templates/ directory."""
    path = _TEMPLATE_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"<html><body><h1>{name} not found</h1></body></html>"


def create_app(server) -> Any:
    """Create FastAPI app with REST API + WebSocket + Web UI."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError("pip install fastapi uvicorn")

    app = FastAPI(title="Toonic Server", version="1.0.0")
    
    # Add CORS middleware for WebSocket support
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    ws_clients: set = set()

    # ── Event broadcaster ────────────────────────────────────

    async def broadcast_event(event):
        """Broadcast server events to all WebSocket clients."""
        data = json.dumps(event.to_dict())
        disconnected = set()
        for client in ws_clients:
            try:
                await client.send_text(data)
            except Exception:
                disconnected.add(client)
        ws_clients -= disconnected

    server.on_event(broadcast_event)

    # ── Web UI ───────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def web_ui():
        return _load_template("web_ui.html")

    @app.get("/events-view", response_class=HTMLResponse)
    async def events_viewer_ui():
        return _load_template("events_viewer.html")

    # ── WebSocket ────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        logger.info("WebSocket connect: /ws")
        await websocket.accept()
        ws_clients.add(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                # Handle client commands via WebSocket
                if msg.get("command") == "analyze":
                    action = await server.analyze_now(
                        goal=msg.get("goal", ""),
                        model=msg.get("model", ""),
                    )
                    await websocket.send_text(json.dumps({
                        "event": "action", "data": action.to_dict(), "timestamp": time.time()
                    }))
        except WebSocketDisconnect:
            logger.info("WebSocket disconnect: /ws")
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            ws_clients.discard(websocket)

    # ── REST API ─────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        return server.get_status()

    @app.get("/api/actions")
    async def get_actions(limit: int = 20):
        return server.get_actions(limit)

    @app.post("/api/analyze")
    async def analyze_now(body: dict = {}):
        action = await server.analyze_now(
            goal=body.get("goal", ""),
            model=body.get("model", ""),
        )
        return action.to_dict()

    @app.post("/api/sources")
    async def add_source(body: dict = {}):
        from toonic.server.config import SourceConfig
        src = SourceConfig(
            path_or_url=body.get("path_or_url", ""),
            category=body.get("category", "code"),
        )
        sid = await server.add_source(src)
        return {"source_id": sid, "status": "added"}

    @app.delete("/api/sources/{source_id}")
    async def remove_source(source_id: str):
        await server.remove_source(source_id)
        return {"source_id": source_id, "status": "removed"}

    @app.post("/api/convert")
    async def convert_file(body: dict = {}):
        """Convert a file to TOON/YAML/JSON spec."""
        from toonic.pipeline import Pipeline
        path = body.get("path", "")
        fmt = body.get("format", "toon")
        try:
            spec = Pipeline.to_spec(path, fmt=fmt)
            tokens = len(spec.split()) * 4 // 3
            return {"spec": spec, "tokens": tokens, "format": fmt}
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    @app.get("/api/formats")
    async def list_formats():
        from toonic.pipeline import Pipeline
        return Pipeline.formats()

    # ── Events + Triggers ───────────────────────────────────

    @app.get("/api/events")
    async def get_events(limit: int = 100, event_type: str = ""):
        """Get recent event log entries."""
        return server.get_event_log(limit=limit, event_type=event_type)

    @app.get("/api/events-file")
    async def get_events_file(
        start: int = 0,
        limit: int = 50,
        event_type: str = "",
        q: str = "",
        max_bytes: int = 2_000_000,
    ):
        """Read persisted events.jsonl with basic pagination."""
        path = Path(getattr(server, "_events_log_path", server.data_dir / "events.jsonl"))
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if start < 0:
            start = 0
        if max_bytes < 50_000:
            max_bytes = 50_000
        if max_bytes > 10_000_000:
            max_bytes = 10_000_000

        if not path.exists():
            return {"items": [], "has_more": False, "next_start": start, "path": str(path)}

        items: List[Dict[str, Any]] = []
        bytes_read = 0
        next_start = start

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            
            # Reverse to get newest first
            all_lines.reverse()
            
            for i, line in enumerate(all_lines):
                bytes_read += len(line.encode("utf-8", errors="ignore"))
                if bytes_read > max_bytes:
                    break

                if i < start:
                    continue

                raw = line.strip()
                next_start = i + 1
                if not raw:
                    continue
                if q and q.lower() not in raw.lower():
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if event_type and obj.get("event") != event_type:
                    continue
                items.append(obj)
                if len(items) >= limit:
                    break
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

        has_more = False
        if len(items) >= limit:
            has_more = True
        elif bytes_read <= max_bytes:
            has_more = False
        else:
            has_more = True

        return {
            "items": items,
            "has_more": has_more,
            "next_start": next_start,
            "path": str(path),
        }

    @app.get("/api/exchanges")
    async def get_exchanges(
        start: int = 0,
        limit: int = 50,
        max_bytes: int = 2_000_000,
    ):
        """Read persisted exchanges.jsonl with basic pagination."""
        path = Path(getattr(server, "_exchanges_log_path", server.data_dir / "exchanges.jsonl"))
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if start < 0:
            start = 0
        if max_bytes < 50_000:
            max_bytes = 50_000
        if max_bytes > 10_000_000:
            max_bytes = 10_000_000

        if not path.exists():
            return {"items": [], "has_more": False, "next_start": start, "path": str(path)}

        items: List[Dict[str, Any]] = []
        bytes_read = 0
        next_start = start

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            
            # Reverse to get newest first
            all_lines.reverse()
            
            for i, line in enumerate(all_lines):
                bytes_read += len(line.encode("utf-8", errors="ignore"))
                if bytes_read > max_bytes:
                    break

                if i < start:
                    continue

                raw = line.strip()
                next_start = i + 1
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                items.append(obj)
                if len(items) >= limit:
                    break
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

        has_more = False
        if len(items) >= limit:
            has_more = True
        elif bytes_read <= max_bytes:
            has_more = False
        else:
            has_more = True

        return {
            "items": items,
            "has_more": has_more,
            "next_start": next_start,
            "path": str(path),
        }

    @app.get("/api/triggers")
    async def get_triggers():
        """Get trigger configuration and stats."""
        from toonic.server.triggers.dsl import TriggerConfig
        cfg = server.trigger_config
        return {
            "config": cfg.to_dict() if cfg else None,
            "stats": server.trigger_scheduler.get_stats(),
        }

    @app.get("/api/data-dir")
    async def get_data_dir():
        """List files in the data directory."""
        data_dir = server.data_dir
        files = []
        for f in sorted(data_dir.rglob("*")):
            if f.is_file():
                files.append({
                    "path": str(f.relative_to(data_dir)),
                    "size_bytes": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                })
        return {
            "data_dir": str(data_dir.resolve()),
            "files": files,
        }

    # ── History + Query ──────────────────────────────────────

    @app.get("/api/history")
    async def get_history(limit: int = 20, category: str = "",
                          model: str = "", action_type: str = ""):
        return server.get_history(limit=limit, category=category,
                                  model=model, action_type=action_type)

    @app.get("/api/history/stats")
    async def get_history_stats():
        return server.get_history_stats()

    @app.post("/api/query")
    async def nlp_query(body: dict = {}):
        """NLP query on conversation history."""
        question = body.get("question", body.get("query", ""))
        if not question:
            return JSONResponse(status_code=400, content={"error": "question required"})
        return await server.nlp_query(question)

    @app.post("/api/sql")
    async def sql_query(body: dict = {}):
        """Raw SQL query on conversation history."""
        sql = body.get("sql", "")
        if not sql:
            return JSONResponse(status_code=400, content={"error": "sql required"})
        return server.sql_query(sql)

    # ── Broxeen Bridge ─────────────────────────────────────
    try:
        from toonic.server.transport.broxeen_bridge import register_broxeen_routes
        register_broxeen_routes(app, server)
    except Exception as e:
        logger.warning(f"Broxeen bridge not loaded: {e}")

    return app
