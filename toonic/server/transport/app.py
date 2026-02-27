"""
FastAPI application factory — creates app with all routes mounted.

REFACTORED: replaces monolithic rest_api.py with modular route files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("toonic.transport.app")

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _load_template(name: str) -> str:
    """Load HTML template from templates/ directory."""
    path = _TEMPLATE_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"<html><body><h1>{name} not found</h1></body></html>"


def create_app(server) -> FastAPI:
    """Create FastAPI app with all routes, WebSocket, and Web UI."""
    app = FastAPI(title="Toonic Server", version="1.0.0")

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

    # ── HTML endpoints ───────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def web_ui():
        return _load_template("web_ui.html")

    @app.get("/events-view", response_class=HTMLResponse)
    async def events_viewer_ui():
        return _load_template("events_viewer.html")

    # ── Mount route modules ──────────────────────────────────

    from toonic.server.transport.routes import api, sources, history, websocket

    api.set_server(server)
    sources.set_server(server)
    history.set_server(server)

    app.include_router(api.router)
    app.include_router(sources.router)
    app.include_router(history.router)
    websocket.register(app, server, ws_clients)

    # ── Broxeen Bridge ───────────────────────────────────────

    try:
        from toonic.server.transport.broxeen_bridge import register_broxeen_routes
        register_broxeen_routes(app, server)
    except Exception as e:
        logger.warning(f"Broxeen bridge not loaded: {e}")

    return app
