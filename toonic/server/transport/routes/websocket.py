"""WebSocket handler — /ws endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger("toonic.transport.routes.websocket")


def register(app: FastAPI, server, ws_clients: set) -> None:
    """Register WebSocket endpoint on the FastAPI app."""

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
