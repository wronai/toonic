"""History + NLP/SQL query endpoints — /api/history, /api/query, /api/sql."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("toonic.transport.routes.history")

router = APIRouter(prefix="/api", tags=["history"])

_server = None


def set_server(server) -> None:
    global _server
    _server = server


def _get_server():
    if _server is None:
        raise RuntimeError("Server not initialized")
    return _server


@router.get("/history")
async def get_history(
    limit: int = 20,
    category: str = "",
    model: str = "",
    action_type: str = "",
):
    return _get_server().get_history(
        limit=limit, category=category, model=model, action_type=action_type
    )


@router.get("/history/stats")
async def get_history_stats():
    return _get_server().get_history_stats()


@router.post("/query")
async def nlp_query(body: dict = {}):
    """NLP query on conversation history."""
    question = body.get("question", body.get("query", ""))
    if not question:
        return JSONResponse(status_code=400, content={"error": "question required"})
    return await _get_server().nlp_query(question)


@router.post("/sql")
async def sql_query(body: dict = {}):
    """Raw SQL query on conversation history."""
    sql = body.get("sql", "")
    if not sql:
        return JSONResponse(status_code=400, content={"error": "sql required"})
    return _get_server().sql_query(sql)
