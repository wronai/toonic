"""
Process Watcher — monitors system processes, ports, and services.

Tracks: running processes, TCP port availability, HTTP health checks,
CPU/memory usage, process restarts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.process")


class ProcessWatcher(BaseWatcher):
    """Watches system processes, ports, and service health."""

    category = SourceCategory.PROCESS

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        self.poll_interval = float(options.get("poll_interval", 10.0))
        self.timeout = float(options.get("timeout", 5.0))

        # Parse target: "proc:nginx", "port:8080", "tcp:host:port", "pid:1234"
        self._target_type, self._target_value = self._parse_target(path_or_url)

        # Health check URL (optional, for service monitoring)
        self.health_url = options.get("health_url", "")

        self._task: asyncio.Task | None = None
        self._check_count: int = 0
        self._prev_state: Dict[str, Any] = {}
        self._state_changes: List[Dict[str, Any]] = []
        self._history: List[Dict[str, Any]] = []

    @staticmethod
    def _parse_target(path_or_url: str) -> Tuple[str, str]:
        """Parse target specification."""
        p = path_or_url.lower()
        if p.startswith("proc:"):
            return "process_name", path_or_url[5:]
        elif p.startswith("pid:"):
            return "pid", path_or_url[4:]
        elif p.startswith("port:"):
            return "port", path_or_url[5:]
        elif p.startswith("tcp:"):
            return "tcp", path_or_url[4:]
        elif p.startswith("service:"):
            return "service", path_or_url[8:]
        elif ":" in p and p.split(":")[-1].isdigit():
            return "tcp", path_or_url
        else:
            return "process_name", path_or_url

    async def start(self) -> None:
        await super().start()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

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
        """Perform check based on target type."""
        self._check_count += 1
        result: Dict[str, Any] = {
            "target_type": self._target_type,
            "target_value": self._target_value,
            "check_number": self._check_count,
            "timestamp": time.time(),
        }

        if self._target_type == "process_name":
            await self._check_process_name(result)
        elif self._target_type == "pid":
            await self._check_pid(result)
        elif self._target_type in ("port", "tcp"):
            await self._check_port(result)
        elif self._target_type == "service":
            await self._check_service(result)

        # Optional health check
        if self.health_url:
            await self._check_health(result)

        # Detect changes
        changes = self._detect_changes(result)
        result["changes"] = changes
        result["has_changes"] = len(changes) > 0

        self._prev_state = result.copy()
        self._history.append(result)
        if len(self._history) > 50:
            self._history = self._history[-50:]

        # Build TOON and emit
        toon = self._to_toon(result)
        is_delta = self._check_count > 1
        should_emit = (
            not is_delta
            or result.get("has_changes", False)
            or self._check_count % 10 == 0
        )

        if should_emit:
            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.PROCESS,
                toon_spec=toon,
                is_delta=is_delta,
                metadata=result,
            ))

    async def _check_process_name(self, result: Dict[str, Any]) -> None:
        """Check if a process with given name is running."""
        name = self._target_value
        procs = await self._find_processes(name)
        result["alive"] = len(procs) > 0
        result["process_count"] = len(procs)
        result["processes"] = procs[:10]  # limit detail

    async def _check_pid(self, result: Dict[str, Any]) -> None:
        """Check if a specific PID is running."""
        pid = int(self._target_value)
        try:
            os.kill(pid, 0)
            result["alive"] = True
            # Read /proc info if available
            proc_info = await self._read_proc_info(pid)
            result.update(proc_info)
        except (ProcessLookupError, PermissionError):
            result["alive"] = False
        except ValueError:
            result["alive"] = False
            result["error"] = f"Invalid PID: {self._target_value}"

    async def _check_port(self, result: Dict[str, Any]) -> None:
        """Check if a TCP port is open."""
        if self._target_type == "tcp" and ":" in self._target_value:
            parts = self._target_value.rsplit(":", 1)
            host = parts[0]
            port = int(parts[1])
        else:
            host = "127.0.0.1"
            port = int(self._target_value)

        loop = asyncio.get_event_loop()
        start = time.monotonic()

        def _check_socket():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            try:
                sock.connect((host, port))
                sock.close()
                return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                return False

        is_open = await loop.run_in_executor(None, _check_socket)
        elapsed = time.monotonic() - start

        result["alive"] = is_open
        result["host"] = host
        result["port"] = port
        result["response_time_ms"] = round(elapsed * 1000, 1)

    async def _check_service(self, result: Dict[str, Any]) -> None:
        """Check systemd/init service status."""
        service_name = self._target_value
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            status = stdout.decode().strip()
            result["alive"] = status == "active"
            result["service_status"] = status
        except FileNotFoundError:
            # No systemctl, try basic process check
            procs = await self._find_processes(service_name)
            result["alive"] = len(procs) > 0
            result["process_count"] = len(procs)
        except asyncio.TimeoutError:
            result["alive"] = False
            result["error"] = "timeout checking service"

    async def _check_health(self, result: Dict[str, Any]) -> None:
        """HTTP health check."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                start = time.monotonic()
                resp = await client.get(self.health_url)
                elapsed = time.monotonic() - start
                result["health_status"] = resp.status_code
                result["health_time_ms"] = round(elapsed * 1000, 1)
                result["health_ok"] = 200 <= resp.status_code < 400
        except ImportError:
            pass
        except Exception as e:
            result["health_ok"] = False
            result["health_error"] = str(e)

    async def _find_processes(self, name: str) -> List[Dict[str, Any]]:
        """Find processes matching name using /proc or ps."""
        procs = []

        # Try /proc first (Linux)
        proc_path = "/proc"
        if os.path.isdir(proc_path):
            for entry in os.listdir(proc_path):
                if not entry.isdigit():
                    continue
                try:
                    cmdline_path = os.path.join(proc_path, entry, "cmdline")
                    with open(cmdline_path, "r") as f:
                        cmdline = f.read().replace("\x00", " ").strip()
                    if name.lower() in cmdline.lower():
                        stat_path = os.path.join(proc_path, entry, "stat")
                        status_path = os.path.join(proc_path, entry, "status")
                        info: Dict[str, Any] = {
                            "pid": int(entry),
                            "cmdline": cmdline[:200],
                        }
                        # Read memory info
                        try:
                            with open(status_path, "r") as f:
                                for line in f:
                                    if line.startswith("VmRSS:"):
                                        info["rss_kb"] = int(line.split()[1])
                                    elif line.startswith("Threads:"):
                                        info["threads"] = int(line.split()[1])
                        except Exception:
                            pass
                        procs.append(info)
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue
            return procs

        # Fallback: ps command
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps", "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode(errors="replace").splitlines()[1:]:
                if name.lower() in line.lower():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        procs.append({
                            "pid": int(parts[1]),
                            "cpu": float(parts[2]),
                            "mem": float(parts[3]),
                            "cmdline": parts[10][:200],
                        })
        except Exception:
            pass

        return procs

    async def _read_proc_info(self, pid: int) -> Dict[str, Any]:
        """Read process info from /proc."""
        info: Dict[str, Any] = {}
        try:
            status_path = f"/proc/{pid}/status"
            if os.path.exists(status_path):
                with open(status_path, "r") as f:
                    for line in f:
                        if line.startswith("Name:"):
                            info["name"] = line.split(":", 1)[1].strip()
                        elif line.startswith("VmRSS:"):
                            info["rss_kb"] = int(line.split()[1])
                        elif line.startswith("Threads:"):
                            info["threads"] = int(line.split()[1])
                        elif line.startswith("State:"):
                            info["state"] = line.split(":", 1)[1].strip()

            cmdline_path = f"/proc/{pid}/cmdline"
            if os.path.exists(cmdline_path):
                with open(cmdline_path, "r") as f:
                    info["cmdline"] = f.read().replace("\x00", " ").strip()[:200]
        except Exception:
            pass
        return info

    def _detect_changes(self, result: Dict[str, Any]) -> List[str]:
        """Detect state changes compared to previous check."""
        changes = []
        prev_alive = self._prev_state.get("alive")
        curr_alive = result.get("alive")

        if prev_alive is not None and prev_alive != curr_alive:
            if curr_alive:
                changes.append("came_alive")
            else:
                changes.append("went_down")

        if "process_count" in result and "process_count" in self._prev_state:
            prev_count = self._prev_state["process_count"]
            curr_count = result["process_count"]
            if prev_count != curr_count:
                changes.append(f"process_count:{prev_count}->{curr_count}")

        if "health_ok" in result and "health_ok" in self._prev_state:
            if self._prev_state["health_ok"] != result["health_ok"]:
                changes.append(f"health:{'ok' if result['health_ok'] else 'fail'}")

        return changes

    def _to_toon(self, result: Dict[str, Any]) -> str:
        """Convert check result to TOON format."""
        alive = result.get("alive", False)
        status_str = "UP" if alive else "DOWN"
        changes = result.get("changes", [])
        change_str = ",".join(changes) if changes else "no_change"
        check_num = result.get("check_number", 0)

        header = (
            f"# {self.source_id} | process-check | "
            f"#{check_num} | {self._target_type}:{self._target_value} | "
            f"{status_str} | {change_str}"
        )

        parts = [header]

        if result.get("error"):
            parts.append(f"ERROR: {result['error']}")

        if result.get("processes"):
            for p in result["processes"][:5]:
                pid = p.get("pid", "?")
                rss = p.get("rss_kb", 0)
                cmd = p.get("cmdline", "")[:100]
                parts.append(f"  PID={pid} RSS={rss}KB {cmd}")

        if result.get("response_time_ms"):
            parts.append(f"RESPONSE: {result['response_time_ms']:.0f}ms")

        if result.get("health_ok") is not None:
            h_status = result.get("health_status", "?")
            h_time = result.get("health_time_ms", 0)
            parts.append(f"HEALTH: {h_status} ({h_time:.0f}ms)")

        if result.get("service_status"):
            parts.append(f"SERVICE: {result['service_status']}")

        return "\n".join(parts)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith(("proc:", "pid:", "port:", "tcp:", "service:")):
            return 0.95
        return 0.0


WatcherRegistry.register(ProcessWatcher)
