"""
Toonic Server — main entry point.

Orchestrates watchers, accumulator, LLM router, and transport layers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from toonic.server.config import ServerConfig, SourceConfig
from toonic.server.models import ActionResponse, ContextChunk, ServerEvent, SourceCategory
from toonic.server.core.accumulator import ContextAccumulator
from toonic.server.core.history import ConversationHistory
from toonic.server.core.query import QueryAdapter
from toonic.server.core.router import LLMRequest, LLMRouter
from toonic.server.triggers.dsl import TriggerConfig, TriggerRule
from toonic.server.triggers.scheduler import TriggerScheduler, TriggerEvent
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

# Ensure watchers are registered
import toonic.server.watchers.file_watcher
import toonic.server.watchers.log_watcher
import toonic.server.watchers.stream_watcher
import toonic.server.watchers.http_watcher
import toonic.server.watchers.directory_watcher
import toonic.server.watchers.docker_watcher
import toonic.server.watchers.process_watcher
import toonic.server.watchers.network_watcher
import toonic.server.watchers.database_watcher

logger = logging.getLogger("toonic.server")


class ToonicServer:
    """Main server — connects watchers → accumulator → LLM router → actions."""

    def __init__(self, config: ServerConfig, trigger_config: TriggerConfig | None = None):
        self.config = config
        self.trigger_config = trigger_config
        self.accumulator = ContextAccumulator(
            max_tokens=config.max_context_tokens,
            allocation=config.token_allocation,
        )
        # Data directory for logs, exchanges, etc.
        self.data_dir = Path(os.environ.get("TOONIC_DATA_DIR", "./toonic_data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "exchanges").mkdir(exist_ok=True)
        (self.data_dir / "sources").mkdir(exist_ok=True)
        # History + Query
        self.history = None
        self.query_adapter = None
        if config.history_enabled:
            db_path = config.history_db_path
            if db_path == "./toonic_history.db":
                db_path = str(self.data_dir / "history.db")
            self.history = ConversationHistory(db_path)
            self.query_adapter = QueryAdapter(self.history)
        # Router (with history for logging)
        self.router = LLMRouter(config, history=self.history)
        # Trigger scheduler
        if trigger_config and trigger_config.triggers:
            self.trigger_scheduler = TriggerScheduler(trigger_config)
        else:
            self.trigger_scheduler = TriggerScheduler.default_periodic(
                interval_s=config.interval if config.interval > 0 else 30.0,
                goal=config.goal,
            )
        self.trigger_scheduler.on_trigger(self._on_trigger_fired)
        self._watchers: Dict[str, BaseWatcher] = {}
        self._watcher_tasks: Dict[str, asyncio.Task] = {}
        self._event_listeners: Set[Callable] = set()
        self._analysis_task: asyncio.Task | None = None
        self._running = False
        self._start_time = 0.0
        self._total_chunks = 0
        self._actions: List[ActionResponse] = []
        self._recent_images: List[str] = []  # base64 JPEG keyframes for multimodal
        self._event_log: List[Dict] = []     # in-memory event log for Web UI
        # Open persistent log files
        self._events_log_path = self.data_dir / "events.jsonl"
        self._exchanges_log_path = self.data_dir / "exchanges.jsonl"

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
        """Consume chunks from a watcher and update accumulator + trigger evaluation."""
        try:
            async for chunk in watcher.get_chunks():
                if not self._running:
                    break
                self.accumulator.update(chunk)
                self._total_chunks += 1
                # Collect base64 images for multimodal analysis
                if chunk.raw_data and chunk.raw_encoding == "base64_jpeg":
                    import base64
                    b64 = base64.b64encode(chunk.raw_data).decode()
                    self._recent_images.append(b64)
                    # Also collect extra images from detection events
                    # (ROI crops, diff overlays, multi-frame sequences)
                    extra = chunk.metadata.get("extra_images_b64", [])
                    self._recent_images.extend(extra)
                    if len(self._recent_images) > 20:
                        self._recent_images = self._recent_images[-20:]
                await self._emit_event("context", chunk.to_dict())
                # Evaluate triggers against this chunk's metadata
                trigger_data = dict(chunk.metadata)
                trigger_data["toon_spec"] = chunk.toon_spec
                cat = chunk.category.value if isinstance(chunk.category, SourceCategory) else chunk.category
                await self.trigger_scheduler.evaluate_async(trigger_data, cat)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{sid}] Consumer error: {e}")

    async def _on_trigger_fired(self, event: TriggerEvent) -> None:
        """Called by TriggerScheduler when a rule fires — runs LLM analysis."""
        goal = event.goal or self.config.goal
        await self._emit_event("trigger", event.to_dict())
        logger.info(f"Trigger '{event.rule_name}' fired ({event.reason}) — analyzing")
        await self._run_analysis(goal_override=goal)

    async def _analysis_loop(self) -> None:
        """Periodic analysis loop — fallback for trigger-driven mode."""
        # With trigger scheduler, the analysis is driven by trigger events.
        # This loop is kept as a safety net / initial analysis.
        await asyncio.sleep(min(5.0, self.config.interval))
        # Run one initial analysis
        try:
            await self._run_analysis()
        except Exception as e:
            logger.error(f"Initial analysis error: {e}")
        # Then let the trigger scheduler handle subsequent analyses
        while self._running:
            await asyncio.sleep(1.0)

    async def _one_shot(self) -> None:
        """Single analysis after initial data collection."""
        await asyncio.sleep(5.0)  # wait for watchers
        await self._run_analysis()

    async def _run_analysis(self, goal_override: str = "") -> None:
        """Build context and query LLM."""
        goal = goal_override or self.config.goal
        context = self.accumulator.get_context(
            goal=goal,
            system_prompt="",
        )
        if not context.strip():
            return

        stats = self.accumulator.get_stats()

        # Determine category and collect images for multimodal
        category = "text"
        images = []
        if stats["per_category"].get("video", {}).get("sources", 0) > 0:
            category = "multimodal"
            # Send up to 8 recent images (event frames + ROI crops + diffs)
            images = list(self._recent_images[-8:])

        request = LLMRequest(
            context=context,
            goal=goal,
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
        """Emit event to all listeners + persist to log files."""
        event = ServerEvent(event_type=event_type, data=data)
        # Keep in-memory log (last 500 events)
        entry = event.to_dict()
        self._event_log.append(entry)
        if len(self._event_log) > 500:
            self._event_log = self._event_log[-500:]
        # Persist to events.jsonl
        try:
            with open(self._events_log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass
        # Persist LLM exchanges to exchanges.jsonl
        if event_type == "action":
            try:
                with open(self._exchanges_log_path, "a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except Exception:
                pass
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
            "total_events": len(self._event_log),
            "data_dir": str(self.data_dir.resolve()),
            "trigger_stats": self.trigger_scheduler.get_stats(),
            "accumulator": self.accumulator.get_stats(),
            "router": self.router.get_stats(),
        }

    def get_event_log(self, limit: int = 100, event_type: str = "") -> List[Dict]:
        """Get recent event log entries."""
        events = self._event_log
        if event_type:
            events = [e for e in events if e.get("event") == event_type]
        return events[-limit:]

    def get_actions(self, limit: int = 20) -> List[Dict]:
        """Get recent actions."""
        return [a.to_dict() for a in self._actions[-limit:]]

    # ── History + Query ───────────────────────────────────────────────

    def get_history(self, limit: int = 20, **filters) -> List[Dict]:
        """Get conversation history."""
        if not self.history:
            return []
        records = self.history.recent(limit=limit, **filters)
        return [r.to_dict() for r in records]

    def get_history_stats(self) -> Dict[str, Any]:
        """Get history statistics."""
        if not self.history:
            return {"enabled": False}
        stats = self.history.stats()
        stats["enabled"] = True
        return stats

    async def nlp_query(self, question: str) -> Dict[str, Any]:
        """Execute NLP query on conversation history."""
        if not self.query_adapter:
            return {"error": "History not enabled"}
        return await self.query_adapter.nlp_query(question)

    def sql_query(self, sql: str) -> Dict[str, Any]:
        """Execute SQL query on conversation history."""
        if not self.query_adapter:
            return {"error": "History not enabled"}
        return self.query_adapter.sql_query(sql)
