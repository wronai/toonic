"""
NLP/SQL Query Adapter — search conversation history via natural language or SQL.

Translates natural language queries into SQL using the LLM, then executes
against the ConversationHistory SQLite database.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from toonic.server.core.history import ConversationHistory

logger = logging.getLogger("toonic.query")

# Schema description for the LLM
SCHEMA_DESCRIPTION = """
Table: exchanges
Columns:
  id TEXT PRIMARY KEY
  timestamp REAL (unix epoch)
  session_id TEXT
  goal TEXT (analysis goal)
  category TEXT (code|config|data|logs|video|audio|document|database|api|infra)
  model TEXT (LLM model name, e.g. google/gemini-3-flash-preview)
  context_tokens INTEGER (tokens in the context sent)
  context_preview TEXT (first 2000 chars of context)
  sources TEXT (JSON array of source_ids)
  images_count INTEGER (number of images sent)
  action_type TEXT (report|code_fix|alert|none|error)
  content TEXT (LLM response content)
  confidence REAL (0.0-1.0)
  target_path TEXT (file path for code_fix)
  affected_files TEXT (JSON array)
  tokens_used INTEGER (total tokens consumed)
  duration_s REAL (response time in seconds)
  status TEXT (ok|error|timeout)
  error_message TEXT
"""

NLP_TO_SQL_PROMPT = (
    "You are a SQL query generator. Given a natural language question about "
    "LLM conversation history, generate a SQLite SELECT query.\n\n"
    f"Database schema:\n{SCHEMA_DESCRIPTION}\n\n"
    "Rules:\n"
    "- Output ONLY the SQL query, nothing else\n"
    "- Always use SELECT, never INSERT/UPDATE/DELETE\n"
    "- Use LIKE for text search, not =\n"
    "- For time, use timestamp > (unix_epoch - seconds)\n"
    "- For 'last hour' use: timestamp > (strftime('%s','now') - 3600)\n"
    "- For 'today' use: date(timestamp, 'unixepoch') = date('now')\n"
    "- Limit results to 50 unless specified\n"
    "- Order by timestamp DESC by default\n"
)


class QueryAdapter:
    """Translates NLP queries to SQL and executes against history DB."""

    def __init__(self, history: ConversationHistory):
        self.history = history

    async def nlp_query(self, question: str, model: str = "") -> Dict[str, Any]:
        """Execute a natural language query on conversation history."""
        start = time.time()

        # Try to handle common patterns without LLM
        sql = self._try_local_parse(question)

        if not sql:
            sql = await self._generate_sql(question, model)

        if not sql:
            return {
                "query": question,
                "sql": "",
                "error": "Could not generate SQL for this query",
                "results": [],
            }

        return self._execute_query(sql, question, start)

    def sql_query(self, sql: str) -> Dict[str, Any]:
        """Execute a raw SQL query on conversation history."""
        start = time.time()
        # Safety: only allow SELECT
        if not sql.strip().upper().startswith("SELECT"):
            return {"error": "Only SELECT queries are allowed", "sql": sql, "results": []}
        return self._execute_query(sql, sql, start)

    def _execute_query(self, sql: str, original_query: str, start: float) -> Dict[str, Any]:
        """Execute SQL and return formatted results."""
        try:
            results = self.history.execute_sql(sql)
            duration = time.time() - start
            return {
                "query": original_query,
                "sql": sql,
                "results": results,
                "count": len(results),
                "duration_s": round(duration, 3),
            }
        except Exception as e:
            return {
                "query": original_query,
                "sql": sql,
                "error": str(e),
                "results": [],
            }

    def _try_local_parse(self, question: str) -> str:
        """Try to parse common query patterns without calling LLM."""
        q = question.lower().strip()

        # "last N" or "recent N"
        m = re.search(r'(?:last|recent)\s+(\d+)', q)
        limit = int(m.group(1)) if m else 50

        # Time filters
        time_filter = ""
        if "last hour" in q or "past hour" in q:
            time_filter = f"timestamp > (strftime('%s','now') - 3600)"
        elif "last day" in q or "today" in q:
            time_filter = f"timestamp > (strftime('%s','now') - 86400)"
        elif "last week" in q:
            time_filter = f"timestamp > (strftime('%s','now') - 604800)"

        # Category filters
        cat_filter = ""
        for cat in ["video", "audio", "code", "config", "logs", "document", "data", "database"]:
            if cat in q:
                cat_filter = f"category = '{cat}'"
                break

        # Status filters
        status_filter = ""
        if "error" in q and "category" not in q:
            status_filter = "status = 'error'"
        elif "success" in q or "ok" in q:
            status_filter = "status = 'ok'"

        # Action type filters
        action_filter = ""
        if "fix" in q or "code_fix" in q:
            action_filter = "action_type = 'code_fix'"
        elif "alert" in q:
            action_filter = "action_type = 'alert'"
        elif "report" in q:
            action_filter = "action_type = 'report'"

        # Model filter
        model_filter = ""
        if "gemini" in q:
            model_filter = "model LIKE '%gemini%'"
        elif "claude" in q:
            model_filter = "model LIKE '%claude%'"
        elif "gpt" in q:
            model_filter = "model LIKE '%gpt%'"

        # Content search
        content_filter = ""
        m = re.search(r'(?:about|containing|with|mentioning)\s+"([^"]+)"', q)
        if m:
            content_filter = f"content LIKE '%{m.group(1)}%'"

        # Aggregate queries
        if any(w in q for w in ["count", "how many", "total"]):
            conditions = [f for f in [time_filter, cat_filter, status_filter, action_filter, model_filter] if f]
            where = " AND ".join(conditions) if conditions else "1=1"
            return f"SELECT COUNT(*) as total, category, status FROM exchanges WHERE {where} GROUP BY category, status"

        if "tokens" in q and ("total" in q or "sum" in q or "usage" in q):
            conditions = [f for f in [time_filter, cat_filter, model_filter] if f]
            where = " AND ".join(conditions) if conditions else "1=1"
            return f"SELECT model, SUM(tokens_used) as total_tokens, COUNT(*) as calls FROM exchanges WHERE {where} GROUP BY model"

        # Build standard SELECT
        conditions = [f for f in [time_filter, cat_filter, status_filter, action_filter, model_filter, content_filter] if f]
        if not conditions and not m:
            return ""  # Can't parse, fall through to LLM

        where = " AND ".join(conditions) if conditions else "1=1"
        return f"SELECT id, datetime(timestamp, 'unixepoch') as time, category, model, action_type, confidence, duration_s, substr(content, 1, 200) as content_preview FROM exchanges WHERE {where} ORDER BY timestamp DESC LIMIT {limit}"

    async def _generate_sql(self, question: str, model: str = "") -> str:
        """Use LLM to generate SQL from natural language question."""
        try:
            import litellm

            api_key = os.environ.get("LLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
            llm_model = model or os.environ.get("LLM_MODEL", "google/gemini-3-flash-preview")

            response = await litellm.acompletion(
                model=llm_model,
                messages=[
                    {"role": "system", "content": NLP_TO_SQL_PROMPT},
                    {"role": "user", "content": question},
                ],
                max_tokens=500,
                api_key=api_key or None,
            )

            sql = response.choices[0].message.content.strip()
            # Extract SQL from markdown code block if present
            if "```" in sql:
                m = re.search(r'```(?:sql)?\s*\n?(.*?)\n?```', sql, re.DOTALL)
                if m:
                    sql = m.group(1).strip()

            # Validate: must be SELECT
            if sql.upper().startswith("SELECT"):
                return sql

            logger.warning(f"LLM generated non-SELECT query: {sql[:100]}")
            return ""

        except ImportError:
            logger.warning("litellm not available for NLP query generation")
            return ""
        except Exception as e:
            logger.error(f"NLP query generation error: {e}")
            return ""
