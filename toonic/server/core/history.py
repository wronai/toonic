"""
Conversation History — SQLite-backed log of all LLM exchanges.

Stores every request/response pair with full metadata for:
- Auditing: verify all exchanges worked correctly
- Search: NLP/SQL queries on metadata
- Replay: reproduce analysis sessions
- Analytics: token usage, latency, model performance
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExchangeRecord:
    """Single LLM exchange record."""
    id: str = ""
    timestamp: float = 0.0
    session_id: str = ""

    # Request
    goal: str = ""
    category: str = ""
    model: str = ""
    context_tokens: int = 0
    context_preview: str = ""
    sources: str = ""               # JSON list of source_ids
    images_count: int = 0

    # Response
    action_type: str = ""
    content: str = ""
    confidence: float = 0.0
    target_path: str = ""
    affected_files: str = ""        # JSON list

    # Metrics
    tokens_used: int = 0
    duration_s: float = 0.0
    status: str = "ok"              # ok|error|timeout
    error_message: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "goal": self.goal,
            "category": self.category,
            "model": self.model,
            "context_tokens": self.context_tokens,
            "context_preview": self.context_preview[:500],
            "sources": json.loads(self.sources) if self.sources else [],
            "images_count": self.images_count,
            "action_type": self.action_type,
            "content": self.content,
            "confidence": self.confidence,
            "target_path": self.target_path,
            "affected_files": json.loads(self.affected_files) if self.affected_files else [],
            "tokens_used": self.tokens_used,
            "duration_s": self.duration_s,
            "status": self.status,
            "error_message": self.error_message,
        }


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS exchanges (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    session_id TEXT DEFAULT '',
    goal TEXT DEFAULT '',
    category TEXT DEFAULT '',
    model TEXT DEFAULT '',
    context_tokens INTEGER DEFAULT 0,
    context_preview TEXT DEFAULT '',
    sources TEXT DEFAULT '[]',
    images_count INTEGER DEFAULT 0,
    action_type TEXT DEFAULT '',
    content TEXT DEFAULT '',
    confidence REAL DEFAULT 0.0,
    target_path TEXT DEFAULT '',
    affected_files TEXT DEFAULT '[]',
    tokens_used INTEGER DEFAULT 0,
    duration_s REAL DEFAULT 0.0,
    status TEXT DEFAULT 'ok',
    error_message TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON exchanges(timestamp);
CREATE INDEX IF NOT EXISTS idx_category ON exchanges(category);
CREATE INDEX IF NOT EXISTS idx_model ON exchanges(model);
CREATE INDEX IF NOT EXISTS idx_action_type ON exchanges(action_type);
CREATE INDEX IF NOT EXISTS idx_status ON exchanges(status);
CREATE INDEX IF NOT EXISTS idx_session ON exchanges(session_id);
"""

_INSERT_SQL = """
INSERT INTO exchanges (
    id, timestamp, session_id, goal, category, model,
    context_tokens, context_preview, sources, images_count,
    action_type, content, confidence, target_path, affected_files,
    tokens_used, duration_s, status, error_message
) VALUES (
    :id, :timestamp, :session_id, :goal, :category, :model,
    :context_tokens, :context_preview, :sources, :images_count,
    :action_type, :content, :confidence, :target_path, :affected_files,
    :tokens_used, :duration_s, :status, :error_message
)
"""


class ConversationHistory:
    """SQLite-backed conversation history for all LLM exchanges."""

    def __init__(self, db_path: str = "./toonic_history.db", session_id: str = ""):
        self.db_path = db_path
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database and create tables."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.executescript(_CREATE_SQL)
            conn.commit()
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, exchange: ExchangeRecord) -> str:
        """Record an exchange. Returns the exchange ID."""
        if not exchange.session_id:
            exchange.session_id = self.session_id
        with self._lock:
            conn = self._conn()
            conn.execute(_INSERT_SQL, {
                "id": exchange.id,
                "timestamp": exchange.timestamp,
                "session_id": exchange.session_id,
                "goal": exchange.goal,
                "category": exchange.category,
                "model": exchange.model,
                "context_tokens": exchange.context_tokens,
                "context_preview": exchange.context_preview[:2000],
                "sources": exchange.sources,
                "images_count": exchange.images_count,
                "action_type": exchange.action_type,
                "content": exchange.content,
                "confidence": exchange.confidence,
                "target_path": exchange.target_path,
                "affected_files": exchange.affected_files,
                "tokens_used": exchange.tokens_used,
                "duration_s": exchange.duration_s,
                "status": exchange.status,
                "error_message": exchange.error_message,
            })
            conn.commit()
            conn.close()
        return exchange.id

    def get(self, exchange_id: str) -> Optional[ExchangeRecord]:
        """Get a single exchange by ID."""
        conn = self._conn()
        row = conn.execute("SELECT * FROM exchanges WHERE id = ?", (exchange_id,)).fetchone()
        conn.close()
        if row:
            return self._row_to_record(row)
        return None

    def recent(self, limit: int = 20, category: str = "",
               model: str = "", action_type: str = "",
               session_id: str = "", status: str = "") -> List[ExchangeRecord]:
        """Get recent exchanges with optional filters."""
        conditions = []
        params = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if model:
            conditions.append("model LIKE ?")
            params.append(f"%{model}%")
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM exchanges WHERE {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [self._row_to_record(r) for r in rows]

    def search(self, query: str = "", since: str = "",
               category: str = "", limit: int = 50) -> List[ExchangeRecord]:
        """Search exchanges by text content and time range."""
        conditions = []
        params = []

        if query:
            conditions.append("(content LIKE ? OR goal LIKE ? OR context_preview LIKE ?)")
            q = f"%{query}%"
            params.extend([q, q, q])

        if since:
            seconds = self._parse_duration(since)
            if seconds > 0:
                conditions.append("timestamp > ?")
                params.append(time.time() - seconds)

        if category:
            conditions.append("category = ?")
            params.append(category)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM exchanges WHERE {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [self._row_to_record(r) for r in rows]

    def execute_sql(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute raw SQL query on the exchanges table."""
        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def stats(self) -> Dict[str, Any]:
        """Get history statistics."""
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) FROM exchanges").fetchone()[0]
        by_category = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM exchanges GROUP BY category"
        ).fetchall()
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt, SUM(tokens_used) as tokens "
            "FROM exchanges GROUP BY model"
        ).fetchall()
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM exchanges GROUP BY status"
        ).fetchall()
        total_tokens = conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM exchanges"
        ).fetchone()[0]
        avg_duration = conn.execute(
            "SELECT COALESCE(AVG(duration_s), 0) FROM exchanges WHERE status='ok'"
        ).fetchone()[0]
        conn.close()

        return {
            "total_exchanges": total,
            "total_tokens": total_tokens,
            "avg_duration_s": round(avg_duration, 2),
            "session_id": self.session_id,
            "db_path": self.db_path,
            "by_category": {r["category"]: r["cnt"] for r in by_category},
            "by_model": {r["model"]: {"count": r["cnt"], "tokens": r["tokens"] or 0}
                         for r in by_model},
            "by_status": {r["status"]: r["cnt"] for r in by_status},
        }

    def clear(self, before_timestamp: float = 0) -> int:
        """Clear history. If before_timestamp given, only clear older records."""
        conn = self._conn()
        if before_timestamp > 0:
            cursor = conn.execute("DELETE FROM exchanges WHERE timestamp < ?", (before_timestamp,))
        else:
            cursor = conn.execute("DELETE FROM exchanges")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count

    def _row_to_record(self, row: sqlite3.Row) -> ExchangeRecord:
        return ExchangeRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            session_id=row["session_id"],
            goal=row["goal"],
            category=row["category"],
            model=row["model"],
            context_tokens=row["context_tokens"],
            context_preview=row["context_preview"],
            sources=row["sources"],
            images_count=row["images_count"],
            action_type=row["action_type"],
            content=row["content"],
            confidence=row["confidence"],
            target_path=row["target_path"],
            affected_files=row["affected_files"],
            tokens_used=row["tokens_used"],
            duration_s=row["duration_s"],
            status=row["status"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _parse_duration(s: str) -> float:
        """Parse duration string: '1h', '30m', '2d', '300s'."""
        s = s.strip().lower()
        try:
            if s.endswith("d"):
                return float(s[:-1]) * 86400
            elif s.endswith("h"):
                return float(s[:-1]) * 3600
            elif s.endswith("m"):
                return float(s[:-1]) * 60
            elif s.endswith("s"):
                return float(s[:-1])
            else:
                return float(s)
        except ValueError:
            return 0.0
