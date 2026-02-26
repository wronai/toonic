"""
Network Watcher — monitors network connectivity, DNS, and endpoints.

Tracks: ping latency, DNS resolution, TCP port scans, bandwidth,
network interface status, route changes.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.network")


class NetworkWatcher(BaseWatcher):
    """Watches network endpoints for connectivity, latency, and DNS resolution."""

    category = SourceCategory.NETWORK

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        # Strip net: prefix
        target = path_or_url
        if target.startswith("net:"):
            target = target[4:]
        elif target.startswith("ping:"):
            target = target[5:]
        elif target.startswith("dns:"):
            target = target[4:]

        self.poll_interval = float(options.get("poll_interval", 15.0))
        self.timeout = float(options.get("timeout", 5.0))
        self.ping_count = int(options.get("ping_count", 3))

        # Parse targets: can be comma-separated list of hosts/IPs
        self.targets: List[str] = [t.strip() for t in target.split(",") if t.strip()]
        # Ports to check per target (optional)
        self.check_ports: List[int] = [
            int(p) for p in str(options.get("ports", "")).split(",") if p.strip().isdigit()
        ]
        self.check_dns = options.get("check_dns", True)
        self.check_ping = options.get("check_ping", True)

        self._task: asyncio.Task | None = None
        self._check_count: int = 0
        self._prev_results: Dict[str, Dict[str, Any]] = {}

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
        """Check all network targets."""
        self._check_count += 1
        all_results: Dict[str, Dict[str, Any]] = {}

        tasks = []
        for target in self.targets:
            tasks.append(self._check_target(target))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for target, result in zip(self.targets, results):
            if isinstance(result, Exception):
                all_results[target] = {"error": str(result), "reachable": False}
            else:
                all_results[target] = result

        # Detect changes
        changes = self._detect_changes(all_results)

        summary = {
            "check_number": self._check_count,
            "targets": len(self.targets),
            "reachable": sum(1 for r in all_results.values() if r.get("reachable", False)),
            "unreachable": sum(1 for r in all_results.values() if not r.get("reachable", False)),
            "results": all_results,
            "changes": changes,
            "has_changes": len(changes) > 0,
        }

        toon = self._to_toon(summary)
        is_delta = self._check_count > 1
        should_emit = (
            not is_delta
            or summary["has_changes"]
            or self._check_count % 10 == 0
        )

        if should_emit:
            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.NETWORK,
                toon_spec=toon,
                is_delta=is_delta,
                metadata=summary,
            ))

        self._prev_results = all_results

    async def _check_target(self, target: str) -> Dict[str, Any]:
        """Check a single network target."""
        result: Dict[str, Any] = {"target": target, "timestamp": time.time()}

        # Parse host:port if present
        host = target
        default_port = None
        if ":" in target and not target.startswith("["):
            parts = target.rsplit(":", 1)
            if parts[1].isdigit():
                host = parts[0]
                default_port = int(parts[1])

        # DNS resolution
        if self.check_dns:
            dns_result = await self._resolve_dns(host)
            result["dns"] = dns_result
            result["resolved_ips"] = dns_result.get("ips", [])

        # Ping
        if self.check_ping:
            ping_result = await self._ping(host)
            result["ping"] = ping_result
            result["reachable"] = ping_result.get("reachable", False)
            result["latency_ms"] = ping_result.get("avg_ms", 0)

        # If no ping was done, check reachability via TCP
        if not self.check_ping:
            result["reachable"] = bool(result.get("dns", {}).get("ips"))

        # Port checks
        ports_to_check = list(self.check_ports)
        if default_port and default_port not in ports_to_check:
            ports_to_check.insert(0, default_port)

        if ports_to_check:
            port_results = await self._check_ports(host, ports_to_check)
            result["ports"] = port_results
            # If any port is open, target is reachable
            if any(pr.get("open") for pr in port_results.values()):
                result["reachable"] = True

        return result

    async def _resolve_dns(self, host: str) -> Dict[str, Any]:
        """Resolve DNS for a hostname."""
        loop = asyncio.get_event_loop()

        def _resolve():
            start = time.monotonic()
            try:
                results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                elapsed = time.monotonic() - start
                ips = list(set(r[4][0] for r in results))
                return {
                    "ips": ips,
                    "resolve_time_ms": round(elapsed * 1000, 1),
                    "success": True,
                }
            except socket.gaierror as e:
                elapsed = time.monotonic() - start
                return {
                    "ips": [],
                    "resolve_time_ms": round(elapsed * 1000, 1),
                    "success": False,
                    "error": str(e),
                }

        return await loop.run_in_executor(None, _resolve)

    async def _ping(self, host: str) -> Dict[str, Any]:
        """Ping a host using system ping command."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", str(self.ping_count), "-W", str(int(self.timeout)),
                host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout + 2
            )
            output = stdout.decode(errors="replace")

            reachable = proc.returncode == 0
            result: Dict[str, Any] = {"reachable": reachable}

            # Parse ping stats
            for line in output.splitlines():
                if "min/avg/max" in line:
                    # Format: rtt min/avg/max/mdev = 1.234/2.345/3.456/0.567 ms
                    parts = line.split("=")
                    if len(parts) >= 2:
                        values = parts[1].strip().split("/")
                        if len(values) >= 3:
                            result["min_ms"] = float(values[0])
                            result["avg_ms"] = float(values[1])
                            result["max_ms"] = float(values[2])
                elif "packet loss" in line:
                    # Extract packet loss percentage
                    import re
                    m = re.search(r'(\d+(?:\.\d+)?)%\s*packet loss', line)
                    if m:
                        result["packet_loss_pct"] = float(m.group(1))

            return result

        except (FileNotFoundError, asyncio.TimeoutError):
            # Fallback: TCP connect to common ports
            return await self._tcp_ping(host)

    async def _tcp_ping(self, host: str) -> Dict[str, Any]:
        """TCP-based ping fallback."""
        loop = asyncio.get_event_loop()

        def _try_connect():
            for port in (80, 443, 22):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                start = time.monotonic()
                try:
                    sock.connect((host, port))
                    elapsed = time.monotonic() - start
                    sock.close()
                    return {"reachable": True, "avg_ms": round(elapsed * 1000, 1), "method": "tcp"}
                except (socket.timeout, ConnectionRefusedError, OSError):
                    continue
                finally:
                    sock.close()
            return {"reachable": False, "method": "tcp"}

        return await loop.run_in_executor(None, _try_connect)

    async def _check_ports(self, host: str, ports: List[int]) -> Dict[int, Dict[str, Any]]:
        """Check if TCP ports are open."""
        results: Dict[int, Dict[str, Any]] = {}
        loop = asyncio.get_event_loop()

        async def _check_single_port(port: int):
            def _connect():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                start = time.monotonic()
                try:
                    sock.connect((host, port))
                    elapsed = time.monotonic() - start
                    sock.close()
                    return {"open": True, "time_ms": round(elapsed * 1000, 1)}
                except (socket.timeout, ConnectionRefusedError, OSError):
                    elapsed = time.monotonic() - start
                    return {"open": False, "time_ms": round(elapsed * 1000, 1)}
                finally:
                    sock.close()

            return port, await loop.run_in_executor(None, _connect)

        tasks = [_check_single_port(p) for p in ports[:50]]
        for coro in asyncio.as_completed(tasks):
            port, result = await coro
            results[port] = result

        return results

    def _detect_changes(self, current: Dict[str, Dict[str, Any]]) -> List[str]:
        """Detect changes from previous results."""
        changes: List[str] = []

        for target, result in current.items():
            prev = self._prev_results.get(target, {})
            prev_reachable = prev.get("reachable")
            curr_reachable = result.get("reachable", False)

            if prev_reachable is not None and prev_reachable != curr_reachable:
                if curr_reachable:
                    changes.append(f"came_up:{target}")
                else:
                    changes.append(f"went_down:{target}")

            # Latency anomaly (>2x)
            prev_latency = prev.get("latency_ms", 0)
            curr_latency = result.get("latency_ms", 0)
            if prev_latency > 0 and curr_latency > 0:
                ratio = curr_latency / prev_latency
                if ratio > 2.0:
                    changes.append(f"latency_spike:{target}:{ratio:.1f}x")

            # Port changes
            prev_ports = prev.get("ports", {})
            curr_ports = result.get("ports", {})
            for port in set(list(prev_ports.keys()) + list(curr_ports.keys())):
                prev_open = prev_ports.get(port, {}).get("open")
                curr_open = curr_ports.get(port, {}).get("open")
                if prev_open is not None and prev_open != curr_open:
                    state = "opened" if curr_open else "closed"
                    changes.append(f"port_{state}:{target}:{port}")

            # DNS changes
            prev_ips = set(prev.get("resolved_ips", []))
            curr_ips = set(result.get("resolved_ips", []))
            if prev_ips and curr_ips and prev_ips != curr_ips:
                changes.append(f"dns_changed:{target}")

        return changes

    def _to_toon(self, summary: Dict[str, Any]) -> str:
        """Convert results to TOON format."""
        reachable = summary.get("reachable", 0)
        unreachable = summary.get("unreachable", 0)
        total = summary.get("targets", 0)
        changes = summary.get("changes", [])
        change_str = ",".join(changes) if changes else "no_change"

        header = (
            f"# {self.source_id} | network-check | "
            f"#{summary.get('check_number', 0)} | "
            f"{reachable}/{total} reachable | {change_str}"
        )

        parts = [header]

        results = summary.get("results", {})
        for target, result in sorted(results.items()):
            is_up = result.get("reachable", False)
            status = "UP" if is_up else "DOWN"
            latency = result.get("latency_ms", 0)

            line = f"  [{status:4s}] {target}"
            if latency:
                line += f" ({latency:.1f}ms)"

            # DNS info
            dns = result.get("dns", {})
            if dns.get("ips"):
                line += f" [{','.join(dns['ips'][:3])}]"

            parts.append(line)

            # Port details
            port_results = result.get("ports", {})
            if port_results:
                open_ports = [str(p) for p, r in sorted(port_results.items()) if r.get("open")]
                closed_ports = [str(p) for p, r in sorted(port_results.items()) if not r.get("open")]
                if open_ports:
                    parts.append(f"    OPEN: {','.join(open_ports)}")
                if closed_ports:
                    parts.append(f"    CLOSED: {','.join(closed_ports)}")

            if result.get("error"):
                parts.append(f"    ERROR: {result['error']}")

        return "\n".join(parts)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith(("net:", "ping:", "dns:", "network:")):
            return 0.95
        return 0.0


WatcherRegistry.register(NetworkWatcher)
