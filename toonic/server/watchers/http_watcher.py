"""
HTTP Watcher — monitors websites, APIs, and health endpoints.

Tracks: status codes, response times, content changes (hash-based),
SSL certificate expiry, keyword detection, redirect chains.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.http")


class HttpWatcher(BaseWatcher):
    """Watches HTTP/HTTPS endpoints for availability, content changes, and performance."""

    category = SourceCategory.WEB

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        self.poll_interval = float(options.get("poll_interval", 30.0))
        self.timeout = float(options.get("timeout", 10.0))
        self.method = options.get("method", "GET").upper()
        self.headers: Dict[str, str] = options.get("headers", {})
        self.expected_status = int(options.get("expected_status", 200))
        self.keywords: List[str] = options.get("keywords", [])
        self.check_ssl = options.get("check_ssl", True)
        self.follow_redirects = options.get("follow_redirects", True)
        self.content_hash_only = options.get("content_hash_only", False)

        self._task: asyncio.Task | None = None
        self._prev_hash: str = ""
        self._prev_status: int = 0
        self._prev_response_time: float = 0.0
        self._check_count: int = 0
        self._error_count: int = 0
        self._change_count: int = 0
        self._ssl_expiry: Optional[datetime] = None
        self._history: List[Dict[str, Any]] = []

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
        # Initial check immediately
        await self._check_endpoint()

        while self.running:
            await asyncio.sleep(self.poll_interval)
            try:
                await self._check_endpoint()
            except Exception as e:
                logger.error(f"[{self.source_id}] Poll error: {e}")

    async def _check_endpoint(self) -> None:
        """Perform HTTP check and emit results."""
        self._check_count += 1
        result: Dict[str, Any] = {
            "url": self.path_or_url,
            "method": self.method,
            "check_number": self._check_count,
            "timestamp": time.time(),
        }

        try:
            status, response_time, body, headers, redirect_chain = await self._fetch()
            result["status_code"] = status
            result["response_time_ms"] = round(response_time * 1000, 1)
            result["content_length"] = len(body)
            result["content_type"] = headers.get("content-type", "unknown")

            if redirect_chain:
                result["redirects"] = redirect_chain

            # Content hash for change detection
            content_hash = hashlib.sha256(body).hexdigest()[:16]
            result["content_hash"] = content_hash

            # Detect changes
            changes: List[str] = []

            if self._prev_status and self._prev_status != status:
                changes.append(f"status:{self._prev_status}->{status}")

            if self._prev_hash and self._prev_hash != content_hash:
                changes.append("content_changed")
                self._change_count += 1

            if status != self.expected_status:
                changes.append(f"unexpected_status:{status}")

            # Response time anomaly (>2x previous)
            if self._prev_response_time > 0:
                ratio = response_time / self._prev_response_time
                if ratio > 2.0:
                    changes.append(f"slow:{ratio:.1f}x")
                result["response_time_ratio"] = round(ratio, 2)

            # Keyword detection
            body_text = body.decode("utf-8", errors="replace")
            if self.keywords:
                found = [kw for kw in self.keywords if kw.lower() in body_text.lower()]
                missing = [kw for kw in self.keywords if kw.lower() not in body_text.lower()]
                if found:
                    result["keywords_found"] = found
                if missing:
                    result["keywords_missing"] = missing
                    changes.append(f"missing_keywords:{len(missing)}")

            # SSL check
            if self.check_ssl and self.path_or_url.startswith("https://"):
                ssl_info = await self._check_ssl_cert()
                if ssl_info:
                    result["ssl"] = ssl_info
                    if ssl_info.get("days_until_expiry", 999) < 30:
                        changes.append(f"ssl_expiring:{ssl_info['days_until_expiry']}d")

            result["changes"] = changes
            result["has_changes"] = len(changes) > 0

            self._prev_hash = content_hash
            self._prev_status = status
            self._prev_response_time = response_time

        except Exception as e:
            self._error_count += 1
            result["error"] = str(e)
            result["changes"] = ["connection_error"]
            result["has_changes"] = True
            logger.warning(f"[{self.source_id}] Check failed: {e}")

        # Track history (last 50 checks)
        self._history.append(result)
        if len(self._history) > 50:
            self._history = self._history[-50:]

        # Build TOON spec
        toon = self._to_toon(result)

        # Determine if this is worth emitting
        is_delta = self._check_count > 1
        should_emit = (
            not is_delta
            or result.get("has_changes", False)
            or self._check_count % 10 == 0  # periodic summary
        )

        if should_emit:
            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.WEB,
                toon_spec=toon,
                is_delta=is_delta,
                metadata=result,
            ))

    async def _fetch(self):
        """Perform HTTP request. Uses httpx if available, falls back to urllib."""
        redirect_chain = []

        try:
            import httpx
            async with httpx.AsyncClient(
                follow_redirects=self.follow_redirects,
                timeout=self.timeout,
                verify=True,
            ) as client:
                start = time.monotonic()
                resp = await client.request(
                    self.method,
                    self.path_or_url,
                    headers=self.headers,
                )
                elapsed = time.monotonic() - start

                if resp.history:
                    redirect_chain = [
                        {"url": str(r.url), "status": r.status_code}
                        for r in resp.history
                    ]

                return (
                    resp.status_code,
                    elapsed,
                    resp.content,
                    dict(resp.headers),
                    redirect_chain,
                )
        except ImportError:
            pass

        # Fallback: urllib (sync, run in executor)
        import urllib.request
        import urllib.error

        loop = asyncio.get_event_loop()

        def _sync_fetch():
            req = urllib.request.Request(self.path_or_url, method=self.method)
            for k, v in self.headers.items():
                req.add_header(k, v)
            start = time.monotonic()
            try:
                resp = urllib.request.urlopen(req, timeout=self.timeout)
                elapsed = time.monotonic() - start
                body = resp.read()
                headers = dict(resp.headers)
                return resp.status, elapsed, body, headers, []
            except urllib.error.HTTPError as e:
                elapsed = time.monotonic() - start
                body = e.read() if hasattr(e, "read") else b""
                return e.code, elapsed, body, dict(e.headers), []

        return await loop.run_in_executor(None, _sync_fetch)

    async def _check_ssl_cert(self) -> Optional[Dict[str, Any]]:
        """Check SSL certificate details."""
        try:
            parsed = urlparse(self.path_or_url)
            hostname = parsed.hostname
            port = parsed.port or 443

            loop = asyncio.get_event_loop()

            def _get_cert():
                import socket
                ctx = ssl.create_default_context()
                with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
                    s.settimeout(self.timeout)
                    s.connect((hostname, port))
                    cert = s.getpeercert()
                    return cert

            cert = await loop.run_in_executor(None, _get_cert)

            if cert:
                not_after = cert.get("notAfter", "")
                if not_after:
                    expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                    expiry = expiry.replace(tzinfo=timezone.utc)
                    days_left = (expiry - datetime.now(timezone.utc)).days
                    self._ssl_expiry = expiry
                    return {
                        "issuer": str(cert.get("issuer", "")),
                        "expires": not_after,
                        "days_until_expiry": days_left,
                        "subject": str(cert.get("subject", "")),
                    }
        except Exception as e:
            return {"error": str(e)}
        return None

    def _to_toon(self, result: Dict[str, Any]) -> str:
        """Convert check result to TOON format."""
        status = result.get("status_code", "ERR")
        rt = result.get("response_time_ms", 0)
        changes = result.get("changes", [])
        check_num = result.get("check_number", 0)

        change_str = ",".join(changes) if changes else "no_change"
        header = (
            f"# {self.source_id} | http-check | "
            f"#{check_num} | {self.method} {status} | "
            f"{rt:.0f}ms | {change_str}"
        )

        parts = [header]

        if result.get("error"):
            parts.append(f"ERROR: {result['error']}")

        if result.get("redirects"):
            chain = " -> ".join(r["url"] for r in result["redirects"])
            parts.append(f"REDIRECTS: {chain}")

        if result.get("keywords_found"):
            parts.append(f"KEYWORDS_FOUND: {', '.join(result['keywords_found'])}")
        if result.get("keywords_missing"):
            parts.append(f"KEYWORDS_MISSING: {', '.join(result['keywords_missing'])}")

        if result.get("ssl"):
            ssl_info = result["ssl"]
            if "days_until_expiry" in ssl_info:
                parts.append(f"SSL: expires in {ssl_info['days_until_expiry']}d ({ssl_info.get('expires', '')})")
            elif "error" in ssl_info:
                parts.append(f"SSL_ERROR: {ssl_info['error']}")

        # Summary stats
        if self._check_count > 1:
            parts.append(
                f"STATS: checks={self._check_count} errors={self._error_count} "
                f"changes={self._change_count}"
            )

        return "\n".join(parts)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith(("http://", "https://")):
            # StreamWatcher takes priority for streams
            if "stream" in p or p.endswith((".m3u8", ".ts")):
                return 0.3
            return 0.85
        if p.startswith("web:"):
            return 0.95
        return 0.0


WatcherRegistry.register(HttpWatcher)
