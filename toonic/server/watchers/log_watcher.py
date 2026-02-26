"""
Log Watcher — tails log files and converts to TOON context.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.log")


class LogWatcher(BaseWatcher):
    """Tails log files and emits TOON-compressed log context."""

    category = SourceCategory.LOGS

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        self.max_lines = int(options.get("max_lines", 100))
        self.poll_interval = float(options.get("poll_interval", 2.0))
        self._last_pos: int = 0
        self._last_size: int = 0
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        await super().start()
        await self._initial_tail()
        self._task = asyncio.create_task(self._tail_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _initial_tail(self) -> None:
        """Read last N lines of log file."""
        path = Path(self.path_or_url)
        if not path.exists():
            logger.warning(f"[{self.source_id}] Log file not found: {path}")
            return

        try:
            content = path.read_text(errors="replace")
            lines = content.strip().split("\n")
            tail = lines[-self.max_lines:]
            self._last_pos = path.stat().st_size
            self._last_size = self._last_pos

            toon = self._to_toon(tail, path.name)
            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.LOGS,
                toon_spec=toon,
                is_delta=False,
                metadata={"path": str(path), "lines": len(tail)},
            ))
            logger.info(f"[{self.source_id}] Initial tail: {len(tail)} lines")
        except Exception as e:
            logger.error(f"[{self.source_id}] Error reading log: {e}")

    async def _tail_loop(self) -> None:
        """Poll for new log lines."""
        while self.running:
            await asyncio.sleep(self.poll_interval)
            try:
                await self._check_new_lines()
            except Exception as e:
                logger.error(f"[{self.source_id}] Tail error: {e}")

    async def _check_new_lines(self) -> None:
        """Check for new lines appended to log file."""
        path = Path(self.path_or_url)
        if not path.exists():
            return

        current_size = path.stat().st_size
        if current_size == self._last_size:
            return

        if current_size < self._last_size:
            # File was truncated/rotated
            self._last_pos = 0
            self._last_size = 0

        try:
            with open(path, "r", errors="replace") as f:
                f.seek(self._last_pos)
                new_content = f.read()
                self._last_pos = f.tell()
                self._last_size = current_size

            if new_content.strip():
                new_lines = new_content.strip().split("\n")
                toon = self._to_toon(new_lines, path.name, delta=True)
                await self.emit(ContextChunk(
                    source_id=self.source_id,
                    category=SourceCategory.LOGS,
                    toon_spec=toon,
                    is_delta=True,
                    metadata={"path": str(path), "new_lines": len(new_lines)},
                ))
        except Exception as e:
            logger.error(f"[{self.source_id}] Read error: {e}")

    def _to_toon(self, lines: list, filename: str, delta: bool = False) -> str:
        """Convert log lines to TOON format."""
        # Categorize log lines
        errors = [l for l in lines if any(x in l.upper() for x in ["ERROR", "FATAL", "CRITICAL"])]
        warnings = [l for l in lines if "WARN" in l.upper()]
        info_count = len(lines) - len(errors) - len(warnings)

        prefix = "DELTA " if delta else ""
        header = (
            f"# {prefix}{filename} | log | {len(lines)}L | "
            f"err:{len(errors)} warn:{len(warnings)} info:{info_count}"
        )

        parts = [header]

        if errors:
            parts.append(f"ERR[{len(errors)}]:")
            for line in errors[-10:]:
                parts.append(f"  {line.strip()[:200]}")

        if warnings:
            parts.append(f"WARN[{len(warnings)}]:")
            for line in warnings[-5:]:
                parts.append(f"  {line.strip()[:200]}")

        # Last few lines for context
        recent = lines[-20:]
        parts.append(f"TAIL[{len(recent)}]:")
        for line in recent:
            parts.append(f"  {line.strip()[:200]}")

        return "\n".join(parts)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith("log:"):
            return 0.95
        if any(x in p for x in [".log", "/logs/", "/log/"]):
            return 0.7
        if p.endswith((".jsonl", ".ndjson")):
            return 0.5
        return 0.0


WatcherRegistry.register(LogWatcher)
