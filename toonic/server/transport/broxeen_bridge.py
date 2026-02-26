"""
Broxeen Bridge — dedicated API endpoints for Broxeen integration.

Exposes a simplified, typed REST API that Broxeen's Tauri/Rust backend
can call to control monitoring, get detection events, and manage watchers.

Endpoints:
    POST /api/broxeen/watch    — start watching a source (RTSP, HTTP, file, dir)
    DELETE /api/broxeen/watch/{id} — stop watching a source
    GET  /api/broxeen/events   — poll recent events (detections, changes, alerts)
    GET  /api/broxeen/snapshot — get latest keyframe from a video source
    GET  /api/broxeen/health   — check toonic server health
    POST /api/broxeen/detect   — one-shot detection on a base64 image or URL
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("toonic.bridge.broxeen")


def register_broxeen_routes(app, server) -> None:
    """Register Broxeen-specific API routes on the FastAPI app."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    # ── Health ────────────────────────────────────────────────

    @app.get("/api/broxeen/health")
    async def broxeen_health():
        """Lightweight health check for Broxeen sidecar management."""
        status = server.get_status()
        return {
            "ok": status.get("running", False),
            "uptime_s": status.get("uptime_s", 0),
            "sources": len(status.get("sources", {})),
            "total_events": status.get("total_events", 0),
            "version": "1.0.0",
        }

    # ── Watch management ─────────────────────────────────────

    @app.post("/api/broxeen/watch")
    async def broxeen_watch(body: dict = {}):
        """Start watching a source.

        Body:
            url: str          — RTSP URL, HTTP URL, or file/dir path
            category: str     — video|web|code|logs|process|container (auto-detected if empty)
            interval_s: float — poll interval (default: 10 for video, 30 for web)
            options: dict     — extra watcher options (scene_threshold, keywords, etc.)
        """
        url = body.get("url", "")
        if not url:
            raise HTTPException(400, "url is required")

        category = body.get("category", "")
        interval = body.get("interval_s", 0)
        options = body.get("options", {})

        # Auto-detect category
        if not category:
            lower = url.lower()
            if lower.startswith("rtsp://"):
                category = "video"
            elif lower.startswith(("http://", "https://")):
                category = "web"
            elif lower.startswith(("docker:", "container:")):
                category = "container"
            elif lower.startswith(("proc:", "process:")):
                category = "process"
            elif any(lower.endswith(ext) for ext in (".log", ".err", ".out")):
                category = "logs"
            else:
                category = "code"

        # Set default intervals per category
        if interval <= 0:
            defaults = {"video": 5, "web": 30, "logs": 5, "code": 60, "container": 15, "process": 10}
            interval = defaults.get(category, 30)

        from toonic.server.config import SourceConfig
        src = SourceConfig(
            path_or_url=url,
            category=category,
            poll_interval=interval,
            options=options,
        )

        sid = await server.add_source(src)
        if not sid:
            raise HTTPException(500, f"Failed to create watcher for: {url}")

        return {
            "source_id": sid,
            "category": category,
            "interval_s": interval,
            "watcher_type": type(server._watchers.get(sid, object)).__name__,
        }

    @app.delete("/api/broxeen/watch/{source_id:path}")
    async def broxeen_unwatch(source_id: str):
        """Stop watching a source."""
        if source_id not in server._watchers:
            raise HTTPException(404, f"Source not found: {source_id}")
        await server.remove_source(source_id)
        return {"source_id": source_id, "status": "stopped"}

    @app.get("/api/broxeen/sources")
    async def broxeen_sources():
        """List all active sources with stats."""
        sources = []
        for sid, watcher in server._watchers.items():
            info = {
                "source_id": sid,
                "type": type(watcher).__name__,
                "category": watcher.category.value if hasattr(watcher.category, "value") else str(watcher.category),
                "url": watcher.path_or_url,
                "running": watcher.running,
            }
            # Add watcher-specific stats
            if hasattr(watcher, "_keyframe_count"):
                info["keyframes"] = watcher._keyframe_count
            if hasattr(watcher, "_frame_count"):
                info["frames"] = watcher._frame_count
            if hasattr(watcher, "_check_count"):
                info["checks"] = watcher._check_count
            if hasattr(watcher, "_error_count"):
                info["errors"] = watcher._error_count
            if hasattr(watcher, "_change_count"):
                info["changes"] = watcher._change_count
            sources.append(info)
        return {"sources": sources}

    # ── Events ───────────────────────────────────────────────

    @app.get("/api/broxeen/events")
    async def broxeen_events(
        limit: int = 50,
        since: float = 0.0,
        event_type: str = "",
        source_id: str = "",
    ):
        """Poll recent events filtered for Broxeen consumption.

        Args:
            limit: max events to return
            since: unix timestamp — only events after this time
            event_type: filter by type (context|trigger|action|error)
            source_id: filter by source
        """
        events = server.get_event_log(limit=limit * 2, event_type=event_type)

        # Apply filters
        if since > 0:
            events = [e for e in events if e.get("timestamp", 0) > since]
        if source_id:
            events = [e for e in events if source_id in str(e.get("data", {}).get("source_id", ""))]

        # Normalize for Broxeen consumption
        normalized = []
        for evt in events[-limit:]:
            data = evt.get("data", {})
            n = {
                "type": evt.get("event", "unknown"),
                "timestamp": evt.get("timestamp", 0),
                "source_id": data.get("source_id", ""),
            }

            # Extract useful fields based on event type
            if evt.get("event") == "context":
                n["category"] = data.get("category", "")
                n["has_image"] = bool(data.get("raw_data"))
                n["scene_score"] = data.get("metadata", {}).get("scene_score", 0)
                n["reason"] = data.get("metadata", {}).get("reason", "")
            elif evt.get("event") == "trigger":
                n["rule"] = data.get("rule_name", data.get("rule", ""))
                n["reason"] = data.get("reason", "")
                n["detections"] = data.get("detections", [])
            elif evt.get("event") == "action":
                n["action_type"] = data.get("action_type", "")
                n["content"] = data.get("content", "")[:500]
                n["model"] = data.get("model_used", "")
                n["confidence"] = data.get("confidence", 0)

            normalized.append(n)

        return {
            "events": normalized,
            "total": len(normalized),
            "server_time": time.time(),
        }

    # ── Snapshot ──────────────────────────────────────────────

    @app.get("/api/broxeen/snapshot")
    async def broxeen_snapshot(source_id: str = ""):
        """Get the latest keyframe (base64 JPEG) from a video source."""
        if not server._recent_images:
            return {"base64": None, "message": "No keyframes captured yet"}

        # If source_id specified, try to find matching image
        # For now, return the most recent one
        b64 = server._recent_images[-1]
        return {
            "base64": b64,
            "timestamp": time.time(),
            "source_id": source_id or "latest",
        }

    # ── One-shot detection ────────────────────────────────────

    @app.post("/api/broxeen/detect")
    async def broxeen_detect(body: dict = {}):
        """One-shot analysis on provided data.

        Body:
            image_base64: str   — base64 JPEG image for visual analysis
            text: str           — text content to analyze
            url: str            — URL to fetch and analyze
            goal: str           — what to look for (default: "describe what you see")
            model: str          — model override
        """
        image_b64 = body.get("image_base64", "")
        text = body.get("text", "")
        url = body.get("url", "")
        goal = body.get("goal", "describe what you see")
        model = body.get("model", "")

        if not image_b64 and not text and not url:
            raise HTTPException(400, "Provide image_base64, text, or url")

        from toonic.server.core.router import LLMRequest

        # Build context
        context_parts = [f"Goal: {goal}"]
        images = []
        category = "text"

        if image_b64:
            images.append(image_b64)
            category = "multimodal"
            context_parts.append("[Image provided for analysis]")

        if text:
            context_parts.append(f"Content:\n{text[:4000]}")

        if url:
            # Quick fetch
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    context_parts.append(f"URL: {url}\nStatus: {resp.status_code}\nContent:\n{resp.text[:4000]}")
            except Exception as e:
                context_parts.append(f"URL: {url}\nFetch error: {e}")

        request = LLMRequest(
            context="\n\n".join(context_parts),
            goal=goal,
            category=category,
            images=images,
            model_override=model,
        )

        action = await server.router.query(request)

        return {
            "action_type": action.action_type,
            "content": action.content,
            "model": action.model_used,
            "confidence": action.confidence,
            "duration_s": action.duration_s,
            "tokens_used": action.tokens_used,
        }

    logger.info("Broxeen bridge API routes registered")
