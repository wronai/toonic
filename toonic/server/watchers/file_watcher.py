"""
File Watcher — monitors directories for changes, converts to TOON.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Dict, Set

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.file")


class FileWatcher(BaseWatcher):
    """Watches a directory for file changes, converts to TOON specs."""

    category = SourceCategory.CODE

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        self.poll_interval = float(options.get("poll_interval", 2.0))
        self._file_hashes: Dict[str, str] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        await super().start()
        # Initial full scan
        await self._full_scan()
        # Start polling for changes
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _full_scan(self) -> None:
        """Initial scan — generate full TOON spec for all files."""
        path = Path(self.path_or_url)
        if not path.exists():
            logger.warning(f"[{self.source_id}] Path does not exist: {path}")
            return

        if path.is_file():
            spec = await self._convert_file(path)
            if spec:
                await self.emit(ContextChunk(
                    source_id=self.source_id,
                    category=self._detect_category(path),
                    toon_spec=spec,
                    is_delta=False,
                    metadata={"path": str(path), "scan": "full"},
                ))
            return

        # Directory scan
        specs = []
        for fpath in sorted(path.rglob("*")):
            if not fpath.is_file():
                continue
            if self._should_skip(fpath):
                continue
            spec = await self._convert_file(fpath)
            if spec:
                specs.append(spec)
                h = hashlib.md5(fpath.read_bytes()[:4096]).hexdigest()[:12]
                self._file_hashes[str(fpath)] = h

        if specs:
            combined = "\n".join(specs)
            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=self._detect_category(path),
                toon_spec=combined,
                is_delta=False,
                metadata={"path": str(path), "files": len(specs), "scan": "full"},
            ))
            logger.info(f"[{self.source_id}] Full scan: {len(specs)} files")

    async def _poll_loop(self) -> None:
        """Poll for file changes."""
        while self.running:
            await asyncio.sleep(self.poll_interval)
            try:
                await self._check_changes()
            except Exception as e:
                logger.error(f"[{self.source_id}] Poll error: {e}")

    async def _check_changes(self) -> None:
        """Check for changed files and emit deltas."""
        path = Path(self.path_or_url)
        if not path.exists():
            return

        files = [path] if path.is_file() else sorted(path.rglob("*"))
        for fpath in files:
            if not fpath.is_file() or self._should_skip(fpath):
                continue
            try:
                h = hashlib.md5(fpath.read_bytes()[:4096]).hexdigest()[:12]
            except (OSError, PermissionError):
                continue
            old_h = self._file_hashes.get(str(fpath))
            if old_h != h:
                self._file_hashes[str(fpath)] = h
                spec = await self._convert_file(fpath)
                if spec:
                    await self.emit(ContextChunk(
                        source_id=f"{self.source_id}:{fpath.name}",
                        category=self._detect_category(fpath),
                        toon_spec=spec,
                        is_delta=True,
                        metadata={"path": str(fpath), "change": "modified"},
                    ))
                    logger.info(f"[{self.source_id}] Changed: {fpath.name}")

    async def _convert_file(self, fpath: Path) -> str:
        """Convert file to TOON spec using toonic pipeline."""
        try:
            from toonic.pipeline import Pipeline
            return Pipeline.to_spec(str(fpath), fmt="toon")
        except Exception:
            # Fallback: basic file info
            try:
                content = fpath.read_text(errors="replace")[:2000]
                lines = content.count("\n") + 1
                return f"# {fpath.name} | {fpath.suffix} | {lines}L\n{content[:500]}"
            except Exception:
                return ""

    def _detect_category(self, path: Path) -> SourceCategory:
        """Detect source category from path."""
        s = str(path).lower()
        if any(x in s for x in ["config", ".env", "docker", "compose"]):
            return SourceCategory.CONFIG
        if any(x in s for x in [".sql"]):
            return SourceCategory.DATABASE
        if any(x in s for x in [".md", ".rst", ".txt", "readme", "doc"]):
            return SourceCategory.DOCUMENT
        if any(x in s for x in [".csv", ".json", ".xml"]):
            return SourceCategory.DATA
        return SourceCategory.CODE

    def _should_skip(self, path: Path) -> bool:
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
        skip_exts = {".pyc", ".pyo", ".so", ".o", ".a", ".dll", ".exe", ".bin", ".png", ".jpg", ".gif", ".ico"}
        parts = set(path.parts)
        if parts & skip_dirs:
            return True
        if path.suffix in skip_exts:
            return True
        if path.name.startswith("."):
            return True
        return False

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        if path_or_url.startswith(("rtsp://", "http://", "ws://", "mqtt://")):
            return 0.0
        p = Path(path_or_url)
        if p.exists():
            return 0.8
        return 0.3


WatcherRegistry.register(FileWatcher)
