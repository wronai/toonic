"""
Base watcher protocol and registry.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Type

from toonic.server.models import ContextChunk, SourceCategory

logger = logging.getLogger("toonic.watcher")


class BaseWatcher:
    """Base class for all data source watchers."""

    source_id: str = ""
    category: SourceCategory = SourceCategory.CODE
    requires: tuple = ()

    def __init__(self, source_id: str, path_or_url: str, **options):
        self.source_id = source_id
        self.path_or_url = path_or_url
        self.options = options
        self.running = False
        self._queue: asyncio.Queue[ContextChunk] = asyncio.Queue(maxsize=100)

    async def start(self) -> None:
        """Start watching the source."""
        self.running = True
        logger.info(f"[{self.source_id}] Started")

    async def stop(self) -> None:
        """Stop watching."""
        self.running = False
        logger.info(f"[{self.source_id}] Stopped")

    async def get_chunks(self) -> AsyncIterator[ContextChunk]:
        """Yield context chunks as they arrive."""
        while self.running:
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield chunk
            except asyncio.TimeoutError:
                continue

    async def emit(self, chunk: ContextChunk) -> None:
        """Emit a chunk to the queue."""
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            # Drop oldest
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(chunk)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        """0.0-1.0 confidence that this watcher handles this source."""
        return 0.0


class WatcherRegistry:
    """Registry of available watchers."""

    _watchers: List[Type[BaseWatcher]] = []

    @classmethod
    def register(cls, watcher_cls: Type[BaseWatcher]) -> None:
        cls._watchers.append(watcher_cls)

    @classmethod
    def resolve(cls, path_or_url: str) -> Optional[Type[BaseWatcher]]:
        scores = [(w.supports(path_or_url), w) for w in cls._watchers]
        if not scores:
            return None
        best_score, best_cls = max(scores, key=lambda x: x[0])
        return best_cls if best_score > 0.0 else None

    @classmethod
    def create(cls, source_id: str, category: str, path_or_url: str, **options) -> Optional[BaseWatcher]:
        """Create appropriate watcher for the source."""
        watcher_cls = cls.resolve(path_or_url)
        if watcher_cls:
            w = watcher_cls(source_id, path_or_url, **options)
            return w

        # Fallback by category
        from toonic.server.watchers.file_watcher import FileWatcher
        from toonic.server.watchers.log_watcher import LogWatcher
        from toonic.server.watchers.stream_watcher import StreamWatcher

        if category in ("logs",):
            return LogWatcher(source_id, path_or_url, **options)
        elif category in ("video", "audio"):
            return StreamWatcher(source_id, path_or_url, **options)
        else:
            return FileWatcher(source_id, path_or_url, **options)

    @classmethod
    def list_all(cls) -> List[str]:
        return [w.__name__ for w in cls._watchers]
