"""
Database Watcher — monitors databases for changes via SQL queries.

Tracks: row counts, schema changes, query result diffs,
connection health, slow queries.
Supports SQLite natively, PostgreSQL/MySQL via optional drivers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.database")


class DatabaseWatcher(BaseWatcher):
    """Watches databases for schema changes, row count changes, and query result diffs."""

    category = SourceCategory.DATABASE

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        # Strip db: or sqlite: prefix
        self._dsn = path_or_url
        for prefix in ("db:", "sqlite:", "database:"):
            if self._dsn.startswith(prefix):
                self._dsn = self._dsn[len(prefix):]
                break

        self.poll_interval = float(options.get("poll_interval", 30.0))
        self.track_schema = options.get("track_schema", True)
        self.track_row_counts = options.get("track_row_counts", True)
        self.custom_queries: List[Dict[str, str]] = options.get("queries", [])
        self.timeout = float(options.get("timeout", 10.0))

        self._task: asyncio.Task | None = None
        self._check_count: int = 0
        self._prev_schema_hash: str = ""
        self._prev_row_counts: Dict[str, int] = {}
        self._prev_query_hashes: Dict[str, str] = {}
        self._db_type: str = self._detect_db_type()

    def _detect_db_type(self) -> str:
        """Detect database type from DSN."""
        dsn = self._dsn.lower()
        if dsn.endswith((".db", ".sqlite", ".sqlite3")) or dsn.startswith("sqlite"):
            return "sqlite"
        if dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
            return "postgresql"
        if dsn.startswith("mysql://"):
            return "mysql"
        if Path(self._dsn).exists() and Path(self._dsn).suffix in (".db", ".sqlite", ".sqlite3"):
            return "sqlite"
        return "sqlite"

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
        """Perform database check."""
        self._check_count += 1
        result: Dict[str, Any] = {
            "dsn": self._dsn,
            "db_type": self._db_type,
            "check_number": self._check_count,
            "timestamp": time.time(),
        }

        try:
            if self._db_type == "sqlite":
                await self._check_sqlite(result)
            elif self._db_type == "postgresql":
                await self._check_postgresql(result)
            else:
                result["error"] = f"Unsupported database type: {self._db_type}"

        except Exception as e:
            result["error"] = str(e)
            result["alive"] = False
            logger.warning(f"[{self.source_id}] Check failed: {e}")

        # Detect changes
        changes = self._detect_changes(result)
        result["changes"] = changes
        result["has_changes"] = len(changes) > 0

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
                category=SourceCategory.DATABASE,
                toon_spec=toon,
                is_delta=is_delta,
                metadata=result,
            ))

    async def _check_sqlite(self, result: Dict[str, Any]) -> None:
        """Check SQLite database."""
        db_path = Path(self._dsn)
        if not db_path.exists():
            result["alive"] = False
            result["error"] = f"Database file not found: {self._dsn}"
            return

        result["alive"] = True
        result["file_size"] = db_path.stat().st_size

        loop = asyncio.get_event_loop()

        def _query():
            conn = sqlite3.connect(str(db_path), timeout=self.timeout)
            conn.row_factory = sqlite3.Row
            try:
                data: Dict[str, Any] = {}

                # Get tables
                cursor = conn.execute(
                    "SELECT name, type FROM sqlite_master "
                    "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
                tables = [{"name": row[0], "type": row[1]} for row in cursor.fetchall()]
                data["tables"] = tables

                # Schema hash
                cursor = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
                )
                schema_sql = "\n".join(row[0] for row in cursor.fetchall())
                data["schema_hash"] = hashlib.sha256(schema_sql.encode()).hexdigest()[:16]
                data["schema_sql"] = schema_sql

                # Row counts
                if self.track_row_counts:
                    row_counts: Dict[str, int] = {}
                    for table in tables:
                        if table["type"] == "table":
                            try:
                                cursor = conn.execute(f'SELECT COUNT(*) FROM "{table["name"]}"')
                                row_counts[table["name"]] = cursor.fetchone()[0]
                            except Exception:
                                row_counts[table["name"]] = -1
                    data["row_counts"] = row_counts

                # Custom queries
                if self.custom_queries:
                    query_results: Dict[str, Any] = {}
                    for q in self.custom_queries:
                        name = q.get("name", q.get("sql", "")[:30])
                        sql = q.get("sql", "")
                        if not sql:
                            continue
                        try:
                            start = time.monotonic()
                            cursor = conn.execute(sql)
                            rows = cursor.fetchall()
                            elapsed = time.monotonic() - start
                            cols = [desc[0] for desc in cursor.description] if cursor.description else []
                            row_data = [dict(zip(cols, row)) for row in rows[:50]]
                            result_hash = hashlib.sha256(
                                json.dumps(row_data, default=str).encode()
                            ).hexdigest()[:16]
                            query_results[name] = {
                                "rows": len(rows),
                                "columns": cols,
                                "data": row_data[:10],
                                "hash": result_hash,
                                "time_ms": round(elapsed * 1000, 1),
                            }
                        except Exception as e:
                            query_results[name] = {"error": str(e)}
                    data["query_results"] = query_results

                # Database stats
                try:
                    cursor = conn.execute("PRAGMA page_count")
                    page_count = cursor.fetchone()[0]
                    cursor = conn.execute("PRAGMA page_size")
                    page_size = cursor.fetchone()[0]
                    data["db_size_pages"] = page_count
                    data["db_page_size"] = page_size
                except Exception:
                    pass

                return data
            finally:
                conn.close()

        db_data = await loop.run_in_executor(None, _query)
        result.update(db_data)

    async def _check_postgresql(self, result: Dict[str, Any]) -> None:
        """Check PostgreSQL database (requires asyncpg or psycopg2)."""
        try:
            import asyncpg
            conn = await asyncio.wait_for(
                asyncpg.connect(self._dsn),
                timeout=self.timeout,
            )
            try:
                result["alive"] = True

                # Get tables
                rows = await conn.fetch(
                    "SELECT table_name, table_type FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
                tables = [{"name": r["table_name"], "type": r["table_type"]} for r in rows]
                result["tables"] = tables

                # Row counts
                if self.track_row_counts:
                    row_counts: Dict[str, int] = {}
                    for table in tables:
                        try:
                            row = await conn.fetchrow(f'SELECT COUNT(*) as cnt FROM "{table["name"]}"')
                            row_counts[table["name"]] = row["cnt"]
                        except Exception:
                            row_counts[table["name"]] = -1
                    result["row_counts"] = row_counts

                # Database size
                row = await conn.fetchrow(
                    "SELECT pg_database_size(current_database()) as size"
                )
                if row:
                    result["db_size_bytes"] = row["size"]

            finally:
                await conn.close()

        except ImportError:
            result["error"] = "asyncpg not installed (pip install asyncpg)"
            result["alive"] = False

    def _detect_changes(self, result: Dict[str, Any]) -> List[str]:
        """Detect changes compared to previous check."""
        changes: List[str] = []

        # Schema change
        schema_hash = result.get("schema_hash", "")
        if self._prev_schema_hash and schema_hash != self._prev_schema_hash:
            changes.append("schema_changed")
        if schema_hash:
            self._prev_schema_hash = schema_hash

        # Row count changes
        row_counts = result.get("row_counts", {})
        for table, count in row_counts.items():
            prev_count = self._prev_row_counts.get(table)
            if prev_count is not None and prev_count != count:
                diff = count - prev_count
                sign = "+" if diff > 0 else ""
                changes.append(f"rows:{table}:{sign}{diff}")
        if row_counts:
            self._prev_row_counts = row_counts.copy()

        # New/removed tables
        if self._check_count > 1:
            prev_tables = set(self._prev_row_counts.keys())
            curr_tables = set(row_counts.keys())
            for t in curr_tables - prev_tables:
                changes.append(f"new_table:{t}")
            for t in prev_tables - curr_tables:
                changes.append(f"dropped_table:{t}")

        # Query result changes
        query_results = result.get("query_results", {})
        for name, qr in query_results.items():
            h = qr.get("hash", "")
            prev_h = self._prev_query_hashes.get(name, "")
            if prev_h and h != prev_h:
                changes.append(f"query_changed:{name}")
            if h:
                self._prev_query_hashes[name] = h

        # Connection state
        alive = result.get("alive", False)
        if self._check_count > 1 and not alive:
            changes.append("connection_lost")

        return changes

    def _to_toon(self, result: Dict[str, Any]) -> str:
        """Convert check result to TOON format."""
        alive = result.get("alive", False)
        status = "UP" if alive else "DOWN"
        changes = result.get("changes", [])
        change_str = ",".join(changes) if changes else "no_change"
        tables = result.get("tables", [])
        check_num = result.get("check_number", 0)

        header = (
            f"# {self.source_id} | db-check | "
            f"#{check_num} | {self._db_type} | "
            f"{status} | {len(tables)} tables | {change_str}"
        )

        parts = [header]

        if result.get("error"):
            parts.append(f"ERROR: {result['error']}")

        if result.get("file_size"):
            size_mb = result["file_size"] / (1024 * 1024)
            parts.append(f"SIZE: {size_mb:.1f}MB")

        # Table row counts
        row_counts = result.get("row_counts", {})
        if row_counts:
            parts.append("TABLES:")
            for table, count in sorted(row_counts.items()):
                prev = self._prev_row_counts.get(table)
                delta = ""
                if prev is not None and prev != count:
                    diff = count - prev
                    delta = f" ({'+' if diff > 0 else ''}{diff})"
                parts.append(f"  {table}: {count} rows{delta}")

        # Custom query results
        query_results = result.get("query_results", {})
        if query_results:
            parts.append("QUERIES:")
            for name, qr in query_results.items():
                if "error" in qr:
                    parts.append(f"  {name}: ERROR {qr['error']}")
                else:
                    parts.append(
                        f"  {name}: {qr.get('rows', 0)} rows "
                        f"({qr.get('time_ms', 0):.0f}ms)"
                    )
                    # Show first few rows
                    for row in qr.get("data", [])[:3]:
                        parts.append(f"    {json.dumps(row, default=str)[:150]}")

        return "\n".join(parts)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith(("db:", "sqlite:", "database:")):
            return 0.95
        if p.startswith(("postgresql://", "postgres://", "mysql://")):
            return 0.90
        if p.endswith((".db", ".sqlite", ".sqlite3")):
            return 0.85
        return 0.0


WatcherRegistry.register(DatabaseWatcher)
