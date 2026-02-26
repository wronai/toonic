"""
Directory Watcher — monitors directory structure for changes.

Tracks: new files, deleted files, moved/renamed files, size changes,
permission changes, directory tree structure diffs.
Unlike FileWatcher (which reads file contents), this focuses on
structural changes and metadata.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.directory")


class DirectoryWatcher(BaseWatcher):
    """Watches directory trees for structural changes (new/deleted/moved files)."""

    category = SourceCategory.DATA

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        # Strip dir: prefix if present
        if path_or_url.startswith("dir:"):
            self.path_or_url = path_or_url[4:]

        self.poll_interval = float(options.get("poll_interval", 5.0))
        self.recursive = options.get("recursive", True)
        self.max_depth = int(options.get("max_depth", 10))
        self.include_hidden = options.get("include_hidden", False)
        self.track_sizes = options.get("track_sizes", True)
        self.track_permissions = options.get("track_permissions", False)
        self.ignore_patterns: List[str] = options.get("ignore_patterns", [
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".idea", ".vscode", "dist", "build", ".DS_Store",
        ])

        self._task: asyncio.Task | None = None
        self._snapshot: Dict[str, Dict[str, Any]] = {}  # path -> file info
        self._scan_count: int = 0
        self._total_created: int = 0
        self._total_deleted: int = 0
        self._total_modified: int = 0

    async def start(self) -> None:
        await super().start()
        # Initial snapshot
        await self._initial_scan()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _initial_scan(self) -> None:
        """Take initial directory snapshot and emit structure."""
        self._snapshot = await self._take_snapshot()
        self._scan_count = 1

        # Emit initial structure
        toon = self._build_tree_toon(self._snapshot)
        await self.emit(ContextChunk(
            source_id=self.source_id,
            category=SourceCategory.DATA,
            toon_spec=toon,
            is_delta=False,
            metadata={
                "path": self.path_or_url,
                "total_files": len(self._snapshot),
                "total_size": sum(f.get("size", 0) for f in self._snapshot.values()),
                "scan": "initial",
            },
        ))
        logger.info(f"[{self.source_id}] Initial scan: {len(self._snapshot)} entries")

    async def _poll_loop(self) -> None:
        """Poll for structural changes."""
        while self.running:
            await asyncio.sleep(self.poll_interval)
            try:
                await self._check_changes()
            except Exception as e:
                logger.error(f"[{self.source_id}] Poll error: {e}")

    async def _check_changes(self) -> None:
        """Compare current state with snapshot, detect changes."""
        self._scan_count += 1
        current = await self._take_snapshot()

        old_paths = set(self._snapshot.keys())
        new_paths = set(current.keys())

        created = new_paths - old_paths
        deleted = old_paths - new_paths
        common = old_paths & new_paths

        # Check for modifications in common files
        modified: List[Tuple[str, Dict[str, Any]]] = []
        for path in common:
            old_info = self._snapshot[path]
            new_info = current[path]
            changes = []
            if self.track_sizes and old_info.get("size") != new_info.get("size"):
                changes.append(f"size:{old_info.get('size', 0)}->{new_info.get('size', 0)}")
            if old_info.get("mtime", 0) != new_info.get("mtime", 0):
                changes.append("mtime_changed")
            if self.track_permissions and old_info.get("mode") != new_info.get("mode"):
                changes.append(f"perms:{old_info.get('mode_str', '')}->{new_info.get('mode_str', '')}")
            if old_info.get("type") != new_info.get("type"):
                changes.append(f"type:{old_info.get('type', '')}->{new_info.get('type', '')}")
            if changes:
                modified.append((path, {"changes": changes, "old": old_info, "new": new_info}))

        # Detect possible renames (same size + close mtime)
        renames: List[Tuple[str, str]] = []
        unmatched_created = set(created)
        unmatched_deleted = set(deleted)
        for d_path in list(unmatched_deleted):
            d_info = self._snapshot[d_path]
            for c_path in list(unmatched_created):
                c_info = current[c_path]
                if (d_info.get("size") == c_info.get("size") and
                        d_info.get("type") == c_info.get("type") and
                        abs(d_info.get("mtime", 0) - c_info.get("mtime", 0)) < 2):
                    renames.append((d_path, c_path))
                    unmatched_created.discard(c_path)
                    unmatched_deleted.discard(d_path)
                    break

        has_changes = bool(unmatched_created or unmatched_deleted or modified or renames)

        if has_changes:
            self._total_created += len(unmatched_created)
            self._total_deleted += len(unmatched_deleted)
            self._total_modified += len(modified)

            toon = self._build_diff_toon(
                created=unmatched_created,
                deleted=unmatched_deleted,
                modified=modified,
                renames=renames,
                current=current,
            )

            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.DATA,
                toon_spec=toon,
                is_delta=True,
                metadata={
                    "created": len(unmatched_created),
                    "deleted": len(unmatched_deleted),
                    "modified": len(modified),
                    "renamed": len(renames),
                    "total_files": len(current),
                    "scan_number": self._scan_count,
                },
            ))

        # Update snapshot
        self._snapshot = current

    async def _take_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Take a snapshot of the directory structure."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        root = Path(self.path_or_url)

        if not root.exists():
            logger.warning(f"[{self.source_id}] Path does not exist: {root}")
            return snapshot

        loop = asyncio.get_event_loop()

        def _scan():
            result: Dict[str, Dict[str, Any]] = {}
            try:
                for entry in self._walk(root, depth=0):
                    rel = str(entry.relative_to(root))
                    try:
                        st = entry.stat()
                        info: Dict[str, Any] = {
                            "type": "dir" if entry.is_dir() else "file",
                            "size": st.st_size if entry.is_file() else 0,
                            "mtime": st.st_mtime,
                        }
                        if self.track_permissions:
                            info["mode"] = st.st_mode
                            info["mode_str"] = stat.filemode(st.st_mode)
                        result[rel] = info
                    except (OSError, PermissionError):
                        continue
            except (OSError, PermissionError) as e:
                logger.error(f"Scan error: {e}")
            return result

        return await loop.run_in_executor(None, _scan)

    def _walk(self, path: Path, depth: int) -> List[Path]:
        """Walk directory tree with depth limit and filtering."""
        entries = []
        if depth > self.max_depth:
            return entries

        try:
            for entry in sorted(path.iterdir()):
                if not self.include_hidden and entry.name.startswith("."):
                    continue
                if entry.name in self.ignore_patterns:
                    continue

                entries.append(entry)

                if entry.is_dir() and self.recursive:
                    entries.extend(self._walk(entry, depth + 1))
        except (PermissionError, OSError):
            pass

        return entries

    def _build_tree_toon(self, snapshot: Dict[str, Dict[str, Any]]) -> str:
        """Build initial tree TOON representation."""
        total_size = sum(f.get("size", 0) for f in snapshot.values())
        dirs = sum(1 for f in snapshot.values() if f.get("type") == "dir")
        files = len(snapshot) - dirs

        header = (
            f"# {self.source_id} | dir-structure | "
            f"{files} files {dirs} dirs | "
            f"{self._human_size(total_size)}"
        )

        parts = [header]

        # Build tree view (limited)
        tree_lines = []
        for path in sorted(snapshot.keys())[:100]:
            info = snapshot[path]
            indent = "  " * path.count(os.sep)
            name = Path(path).name
            if info["type"] == "dir":
                tree_lines.append(f"{indent}{name}/")
            else:
                size = self._human_size(info.get("size", 0))
                tree_lines.append(f"{indent}{name} ({size})")

        parts.append("TREE:")
        parts.extend(tree_lines)

        if len(snapshot) > 100:
            parts.append(f"  ... and {len(snapshot) - 100} more entries")

        return "\n".join(parts)

    def _build_diff_toon(
        self,
        created: Set[str],
        deleted: Set[str],
        modified: List[Tuple[str, Dict[str, Any]]],
        renames: List[Tuple[str, str]],
        current: Dict[str, Dict[str, Any]],
    ) -> str:
        """Build diff TOON representation."""
        total_changes = len(created) + len(deleted) + len(modified) + len(renames)
        header = (
            f"# {self.source_id} | dir-change | "
            f"scan:{self._scan_count} | "
            f"+{len(created)} -{len(deleted)} ~{len(modified)} >{len(renames)} | "
            f"total_changes:{total_changes}"
        )

        parts = [header]

        if renames:
            parts.append(f"RENAMED[{len(renames)}]:")
            for old_path, new_path in sorted(renames)[:20]:
                parts.append(f"  {old_path} -> {new_path}")

        if created:
            parts.append(f"CREATED[{len(created)}]:")
            for path in sorted(created)[:30]:
                info = current.get(path, {})
                size = self._human_size(info.get("size", 0))
                parts.append(f"  + {path} ({size})")

        if deleted:
            parts.append(f"DELETED[{len(deleted)}]:")
            for path in sorted(deleted)[:30]:
                parts.append(f"  - {path}")

        if modified:
            parts.append(f"MODIFIED[{len(modified)}]:")
            for path, detail in sorted(modified, key=lambda x: x[0])[:20]:
                changes_str = ", ".join(detail["changes"])
                parts.append(f"  ~ {path} [{changes_str}]")

        # Summary stats
        parts.append(
            f"CUMULATIVE: +{self._total_created} -{self._total_deleted} "
            f"~{self._total_modified} scans:{self._scan_count}"
        )

        return "\n".join(parts)

    @staticmethod
    def _human_size(size: int) -> str:
        """Convert bytes to human-readable size."""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith("dir:"):
            return 0.95
        return 0.0


WatcherRegistry.register(DirectoryWatcher)
