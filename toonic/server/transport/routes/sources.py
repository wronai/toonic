"""Source CRUD endpoints — /api/sources."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("toonic.transport.routes.sources")

router = APIRouter(prefix="/api/sources", tags=["sources"])

_server = None


def set_server(server) -> None:
    global _server
    _server = server


def _get_server():
    if _server is None:
        raise RuntimeError("Server not initialized")
    return _server


@router.get("/")
async def list_sources():
    server = _get_server()
    status = server.get_status()
    return {"sources": status.get("sources", {})}


@router.post("/")
async def add_source(body: dict = {}):
    from toonic.server.config import SourceConfig
    src = SourceConfig(
        path_or_url=body.get("path_or_url", ""),
        category=body.get("category", "code"),
    )
    sid = await _get_server().add_source(src)
    return {"source_id": sid, "status": "added"}


@router.delete("/{source_id}")
async def remove_source(source_id: str):
    await _get_server().remove_source(source_id)
    return {"source_id": source_id, "status": "removed"}
