"""
Toonic Server — main entry point.

Orchestrates watchers, accumulator, LLM router, and transport layers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from toonic.server.config import ServerConfig, SourceConfig
from toonic.server.models import ActionResponse, ContextChunk, ServerEvent, SourceCategory
from toonic.server.core.accumulator import ContextAccumulator
from toonic.server.core.router import LLMRequest, LLMRouter
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

# Ensure watchers are registered
import toonic.server.watchers.file_watcher
import toonic.server.watchers.log_watcher
import toonic.server.watchers.stream_watcher

logger = logging.getLogger("toonic.server")


class ToonicServer:
    """Main server — connects watchers → accumulator → LLM router → actions."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.accumulator = ContextAccumulator(
            max_tokens=config.max_context_tokens,
            allocation=config.token_allocation,
        )
        self.router = LLMRouter(config)
        self._watchers: Dict[str, BaseWatcher] = {}
        self._watcher_tasks: Dict[str, asyncio.Task] = {}
        self._event_listeners: Set[Callable] = set()
        self._analysis_task: asyncio.Task | None = None
        self._running = False
        self._start_time = 0.0
        self._total_chunks = 0
        self._actions: List[ActionResponse] = []

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the server: watchers + analysis loop."""
        self._running = True
        self._start_time = time.time()
        logger.info(f"Toonic Server starting — goal: {self.config.goal}")

        # Add configured sources
        for src in self.config.sources:
            await self.add_source(src)

        # Start analysis loop
        if self.config.interval > 0:
            self._analysis_task = asyncio.create_task(self._analysis_loop())
        else:
            # One-shot mode: wait for initial data, then analyze once
            self._analysis_task = asyncio.create_task(self._one_shot())

        await self._emit_event("status", {"message": "Server started", "sources": len(self._watchers)})

    async def stop(self) -> None:
        """Stop all watchers and tasks."""
        self._running = False

        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass

        for sid, task in self._watcher_tasks.items():
            task.cancel()
        for watcher in self._watchers.values():
            await watcher.stop()

        self._watchers.clear()
        self._watcher_tasks.clear()
        logger.info("Toonic Server stopped")

    # ── Source management ────────────────────────────────────────

    async def add_source(self, src: SourceConfig) -> str:
        """Add a data source. Returns source_id."""
        sid = src.source_id or f"{src.category}:{src.path_or_url}"
        path = src.path_or_url
        if path.startswith("log:"):
            path = path[4:]

        watcher = WatcherRegistry.create(
            source_id=sid,
            category=src.category,
            path_or_url=path,
            poll_interval=src.poll_interval,
            **src.options,
        )
        if not watcher:
            logger.error(f"No watcher for source: {sid} ({src.path_or_url})")
            return ""

        self._watchers[sid] = watcher
        await watcher.start()

        # Start consumer task
        task = asyncio.create_task(self._consume_watcher(sid, watcher))
        self._watcher_tasks[sid] = task

        logger.info(f"Source added: {sid} ({type(watcher).__name__})")
        await self._emit_event("source_added", {"source_id": sid, "type": type(watcher).__name__})
        return sid

    async def remove_source(self, source_id: str) -> None:
        """Remove a data source."""
        if source_id in self._watcher_tasks:
            self._watcher_tasks[source_id].cancel()
            del self._watcher_tasks[source_id]
        if source_id in self._watchers:
            await self._watchers[source_id].stop()
            del self._watchers[source_id]
        logger.info(f"Source removed: {source_id}")

    # ── Internal loops ───────────────────────────────────────────

    async def _consume_watcher(self, sid: str, watcher: BaseWatcher) -> None:
        """Consume chunks from a watcher and update accumulator."""
        try:
            async for chunk in watcher.get_chunks():
                if not self._running:
                    break
                self.accumulator.update(chunk)
                self._total_chunks += 1
                await self._emit_event("context", chunk.to_dict())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{sid}] Consumer error: {e}")

    async def _analysis_loop(self) -> None:
        """Periodic analysis loop — sends context to LLM."""
        # Wait for initial data
        await asyncio.sleep(min(5.0, self.config.interval))

        while self._running:
            try:
                await self._run_analysis()
            except Exception as e:
                logger.error(f"Analysis error: {e}")
            await asyncio.sleep(self.config.interval)

    async def _one_shot(self) -> None:
        """Single analysis after initial data collection."""
        await asyncio.sleep(5.0)  # wait for watchers
        await self._run_analysis()

    async def _run_analysis(self) -> None:
        """Build context and query LLM."""
        context = self.accumulator.get_context(
            goal=self.config.goal,
            system_prompt="",
        )
        if not context.strip():
            return

        # Collect images from video chunks
        images = []
        stats = self.accumulator.get_stats()

        # Determine category for routing
        category = "text"
        if stats["per_category"].get("video", {}).get("sources", 0) > 0:
            category = "multimodal"

        request = LLMRequest(
            context=context,
            goal=self.config.goal,
            category=category,
            images=images,
        )

        await self._emit_event("analysis_start", {
            "context_tokens": stats["total_tokens"],
            "sources": stats["total_sources"],
        })

        action = await self.router.query(request)
        self._actions.append(action)

        await self._emit_event("action", action.to_dict())
        logger.info(f"Analysis complete: {action.action_type} ({action.duration_s:.1f}s)")

    # ── Manual analysis trigger ──────────────────────────────────

    async def analyze_now(self, goal: str = "", model: str = "") -> ActionResponse:
        """Trigger analysis immediately with optional goal/model override."""
        old_goal = self.config.goal
        if goal:
            self.config.goal = goal

        context = self.accumulator.get_context(goal=self.config.goal)
        request = LLMRequest(
            context=context,
            goal=self.config.goal,
            category="text",
            model_override=model,
        )
        action = await self.router.query(request)
        self._actions.append(action)

        self.config.goal = old_goal
        return action

    # ── Event system ─────────────────────────────────────────────

    def on_event(self, callback: Callable) -> None:
        """Register event listener (for WebSocket/SSE broadcast)."""
        self._event_listeners.add(callback)

    def remove_listener(self, callback: Callable) -> None:
        self._event_listeners.discard(callback)

    async def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit event to all listeners."""
        event = ServerEvent(event_type=event_type, data=data)
        for listener in list(self._event_listeners):
            try:
                await listener(event)
            except Exception:
                self._event_listeners.discard(listener)

    # ── Status ───────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get server status."""
        return {
            "running": self._running,
            "uptime_s": round(time.time() - self._start_time, 1) if self._start_time else 0,
            "goal": self.config.goal,
            "sources": {sid: type(w).__name__ for sid, w in self._watchers.items()},
            "total_chunks": self._total_chunks,
            "total_actions": len(self._actions),
            "accumulator": self.accumulator.get_stats(),
            "router": self.router.get_stats(),
        }

    def get_actions(self, limit: int = 20) -> List[Dict]:
        """Get recent actions."""
        return [a.to_dict() for a in self._actions[-limit:]]
