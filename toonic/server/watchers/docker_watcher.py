"""
Docker Watcher — monitors Docker containers, images, and services.

Tracks: container status, resource usage, restarts, image updates,
health checks, log output.
Uses Docker CLI (no SDK dependency required).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.docker")


class DockerWatcher(BaseWatcher):
    """Watches Docker containers for status changes, resource usage, and health."""

    category = SourceCategory.CONTAINER

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        # Strip docker: prefix
        target = path_or_url
        if target.startswith("docker:"):
            target = target[7:]

        self.poll_interval = float(options.get("poll_interval", 15.0))
        self.container_filter = target if target and target != "*" else ""
        self.track_stats = options.get("track_stats", True)
        self.track_logs = options.get("track_logs", False)
        self.log_tail = int(options.get("log_tail", 20))

        self._task: asyncio.Task | None = None
        self._check_count: int = 0
        self._prev_containers: Dict[str, Dict[str, Any]] = {}
        self._docker_available: Optional[bool] = None

    async def start(self) -> None:
        await super().start()
        self._docker_available = await self._check_docker()
        if not self._docker_available:
            logger.warning(f"[{self.source_id}] Docker CLI not available")
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_docker(self) -> bool:
        """Check if Docker CLI is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "version", "--format", "{{.Server.Version}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            return False

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        await self._check()
        while self.running:
            await asyncio.sleep(self.poll_interval)
            try:
                await self._check()
            except Exception as e:
                logger.error(f"[{self.source_id}] Poll error: {e}")

    async def _check(self) -> None:
        """Check Docker containers."""
        self._check_count += 1

        if not self._docker_available:
            if self._check_count == 1:
                await self.emit(ContextChunk(
                    source_id=self.source_id,
                    category=SourceCategory.CONTAINER,
                    toon_spec=f"# {self.source_id} | docker | UNAVAILABLE | Docker CLI not found",
                    is_delta=False,
                    metadata={"error": "docker_not_available"},
                ))
            return

        containers = await self._list_containers()
        changes = self._detect_changes(containers)

        # Get stats if enabled
        if self.track_stats and containers:
            await self._fetch_stats(containers)

        # Get recent logs if enabled
        if self.track_logs and containers:
            await self._fetch_logs(containers)

        result = {
            "check_number": self._check_count,
            "container_count": len(containers),
            "running": sum(1 for c in containers.values() if c.get("state") == "running"),
            "stopped": sum(1 for c in containers.values() if c.get("state") != "running"),
            "changes": changes,
            "has_changes": len(changes) > 0,
            "containers": containers,
        }

        toon = self._to_toon(result)
        is_delta = self._check_count > 1
        should_emit = (
            not is_delta
            or result["has_changes"]
            or self._check_count % 10 == 0
        )

        if should_emit:
            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.CONTAINER,
                toon_spec=toon,
                is_delta=is_delta,
                metadata=result,
            ))

        self._prev_containers = containers

    async def _list_containers(self) -> Dict[str, Dict[str, Any]]:
        """List Docker containers with details."""
        containers: Dict[str, Dict[str, Any]] = {}
        try:
            cmd = [
                "docker", "ps", "-a",
                "--format", '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}",'
                '"status":"{{.Status}}","state":"{{.State}}","ports":"{{.Ports}}",'
                '"created":"{{.CreatedAt}}","size":"{{.Size}}"}',
            ]
            if self.container_filter:
                cmd.extend(["--filter", f"name={self.container_filter}"])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)

            for line in stdout.decode(errors="replace").strip().splitlines():
                if not line.strip():
                    continue
                try:
                    info = json.loads(line)
                    name = info.get("name", info.get("id", "unknown"))
                    containers[name] = info
                except json.JSONDecodeError:
                    continue

        except (FileNotFoundError, asyncio.TimeoutError) as e:
            logger.error(f"[{self.source_id}] Docker list error: {e}")

        return containers

    async def _fetch_stats(self, containers: Dict[str, Dict[str, Any]]) -> None:
        """Fetch resource stats for running containers."""
        running = [name for name, info in containers.items() if info.get("state") == "running"]
        if not running:
            return

        try:
            cmd = [
                "docker", "stats", "--no-stream",
                "--format", '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}",'
                '"mem_perc":"{{.MemPerc}}","net":"{{.NetIO}}","block":"{{.BlockIO}}","pids":"{{.PIDs}}"}',
            ]
            cmd.extend(running[:20])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)

            for line in stdout.decode(errors="replace").strip().splitlines():
                if not line.strip():
                    continue
                try:
                    stats = json.loads(line)
                    name = stats.get("name", "")
                    if name in containers:
                        containers[name]["stats"] = stats
                except json.JSONDecodeError:
                    continue
        except (FileNotFoundError, asyncio.TimeoutError):
            pass

    async def _fetch_logs(self, containers: Dict[str, Dict[str, Any]]) -> None:
        """Fetch recent log lines for running containers."""
        running = [name for name, info in containers.items() if info.get("state") == "running"]

        for name in running[:5]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "logs", "--tail", str(self.log_tail), name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
                containers[name]["recent_logs"] = stdout.decode(errors="replace").strip().splitlines()[-self.log_tail:]
            except (FileNotFoundError, asyncio.TimeoutError):
                pass

    def _detect_changes(self, current: Dict[str, Dict[str, Any]]) -> List[str]:
        """Detect changes between previous and current state."""
        changes: List[str] = []
        prev_names = set(self._prev_containers.keys())
        curr_names = set(current.keys())

        for name in curr_names - prev_names:
            changes.append(f"new_container:{name}")
        for name in prev_names - curr_names:
            changes.append(f"removed_container:{name}")

        for name in prev_names & curr_names:
            prev_state = self._prev_containers[name].get("state", "")
            curr_state = current[name].get("state", "")
            if prev_state != curr_state:
                changes.append(f"state_change:{name}:{prev_state}->{curr_state}")

            prev_image = self._prev_containers[name].get("image", "")
            curr_image = current[name].get("image", "")
            if prev_image != curr_image:
                changes.append(f"image_change:{name}:{prev_image}->{curr_image}")

        return changes

    def _to_toon(self, result: Dict[str, Any]) -> str:
        """Convert check result to TOON format."""
        running = result.get("running", 0)
        stopped = result.get("stopped", 0)
        total = result.get("container_count", 0)
        changes = result.get("changes", [])
        change_str = ",".join(changes) if changes else "no_change"

        header = (
            f"# {self.source_id} | docker | "
            f"#{result.get('check_number', 0)} | "
            f"{running} running {stopped} stopped ({total} total) | "
            f"{change_str}"
        )

        parts = [header]

        containers = result.get("containers", {})
        for name, info in sorted(containers.items()):
            state = info.get("state", "?")
            image = info.get("image", "?")
            status = info.get("status", "")
            line = f"  [{state.upper():8s}] {name} ({image}) {status}"

            stats = info.get("stats", {})
            if stats:
                cpu = stats.get("cpu", "0%")
                mem = stats.get("mem", "0B")
                line += f" | CPU:{cpu} MEM:{mem}"

            parts.append(line)

            # Include recent error logs
            logs = info.get("recent_logs", [])
            error_logs = [l for l in logs if any(x in l.upper() for x in ["ERROR", "FATAL", "PANIC"])]
            for log_line in error_logs[-3:]:
                parts.append(f"    ERR: {log_line[:150]}")

        return "\n".join(parts)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith("docker:"):
            return 0.95
        return 0.0


WatcherRegistry.register(DockerWatcher)
