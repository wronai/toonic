"""REST API endpoints — /api/status, /api/events, /api/analyze, etc."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("toonic.transport.routes.api")

router = APIRouter(prefix="/api", tags=["api"])

# Server instance — set by app.py at startup
_server = None


def set_server(server) -> None:
    global _server
    _server = server


def _get_server():
    if _server is None:
        raise RuntimeError("Server not initialized")
    return _server


@router.get("/status")
async def get_status():
    return _get_server().get_status()


@router.get("/actions")
async def get_actions(limit: int = 20):
    return _get_server().get_actions(limit)


@router.post("/analyze")
async def analyze_now(body: dict = {}):
    action = await _get_server().analyze_now(
        goal=body.get("goal", ""),
        model=body.get("model", ""),
    )
    return action.to_dict()


@router.get("/events")
async def get_events(limit: int = 100, event_type: str = ""):
    """Get recent event log entries."""
    return _get_server().get_event_log(limit=limit, event_type=event_type)


@router.get("/triggers")
async def get_triggers():
    """Get trigger configuration and stats."""
    server = _get_server()
    cfg = server.trigger_config
    return {
        "config": cfg.to_dict() if cfg else None,
        "stats": server.trigger_scheduler.get_stats(),
    }


@router.get("/data-dir")
async def get_data_dir():
    """List files in the data directory."""
    server = _get_server()
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


@router.get("/formats")
async def list_formats():
    from toonic.pipeline import Pipeline
    return Pipeline.formats()


@router.post("/convert")
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


@router.get("/events-file")
async def get_events_file(
    start: int = 0,
    limit: int = 50,
    event_type: str = "",
    q: str = "",
    max_bytes: int = 2_000_000,
):
    """Read persisted events.jsonl with basic pagination."""
    server = _get_server()
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

    has_more = len(items) >= limit or (bytes_read > max_bytes)

    return {
        "items": items,
        "has_more": has_more,
        "next_start": next_start,
        "path": str(path),
    }


@router.get("/exchanges")
async def get_exchanges(
    start: int = 0,
    limit: int = 50,
    max_bytes: int = 2_000_000,
):
    """Read persisted exchanges.jsonl with basic pagination."""
    server = _get_server()
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

    has_more = len(items) >= limit or (bytes_read > max_bytes)

    return {
        "items": items,
        "has_more": has_more,
        "next_start": next_start,
        "path": str(path),
    }
