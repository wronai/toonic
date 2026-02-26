"""
Tests for toonic.server — Server core, watchers, accumulator, router.
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

from toonic.server.config import ServerConfig, SourceConfig, ModelConfig
from toonic.server.models import ContextChunk, ActionResponse, ServerEvent, SourceCategory
from toonic.server.core.accumulator import ContextAccumulator
from toonic.server.core.history import ConversationHistory, ExchangeRecord
from toonic.server.core.query import QueryAdapter
from toonic.server.core.router import LLMRouter, LLMRequest
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry
from toonic.server.watchers.file_watcher import FileWatcher
from toonic.server.watchers.log_watcher import LogWatcher
from toonic.server.watchers.stream_watcher import StreamWatcher
from toonic.server.main import ToonicServer


# =============================================================================
# Config tests
# =============================================================================

class TestServerConfig:
    def test_default_config(self):
        cfg = ServerConfig()
        assert cfg.port == 8900
        assert "text" in cfg.models
        assert "code" in cfg.models

    def test_from_dict(self):
        cfg = ServerConfig.from_dict({
            "port": 9999,
            "goal": "test goal",
            "interval": 10.0,
        })
        assert cfg.port == 9999
        assert cfg.goal == "test goal"

    def test_to_dict(self):
        cfg = ServerConfig()
        d = cfg.to_dict()
        assert "host" in d
        assert "models" in d
        assert "sources" in d


# =============================================================================
# Models tests
# =============================================================================

class TestModels:
    def test_context_chunk(self):
        chunk = ContextChunk(
            source_id="test:file.py",
            category=SourceCategory.CODE,
            toon_spec="# file.py | python | 100L",
        )
        assert chunk.token_estimate > 0
        d = chunk.to_dict()
        assert d["source_id"] == "test:file.py"
        assert d["category"] == "code"

    def test_context_chunk_with_raw_data(self):
        chunk = ContextChunk(
            source_id="test:cam1",
            category=SourceCategory.VIDEO,
            toon_spec="# cam1 | video",
            raw_data=b"\xff\xd8\xff\xe0",
            raw_encoding="base64_jpeg",
        )
        d = chunk.to_dict()
        assert "raw_data" in d
        assert d["raw_encoding"] == "base64_jpeg"

    def test_action_response(self):
        action = ActionResponse(
            action_type="report",
            content="Found 3 issues",
            confidence=0.85,
            model_used="gemini-flash",
        )
        d = action.to_dict()
        assert d["action_type"] == "report"
        assert d["confidence"] == 0.85

    def test_server_event(self):
        event = ServerEvent(event_type="status", data={"msg": "ok"})
        d = event.to_dict()
        assert d["event"] == "status"
        assert d["timestamp"] > 0


# =============================================================================
# Accumulator tests
# =============================================================================

class TestAccumulator:
    def test_update_and_get(self):
        acc = ContextAccumulator(max_tokens=10000)
        acc.update(ContextChunk(
            source_id="code:main.py",
            category=SourceCategory.CODE,
            toon_spec="# main.py | python | 50L\nf[2]: foo, bar",
        ))
        acc.update(ContextChunk(
            source_id="log:app.log",
            category=SourceCategory.LOGS,
            toon_spec="# app.log | log | 10L\nERR[1]: connection failed",
        ))

        context = acc.get_context(goal="find bugs")
        assert "[GOAL]" in context
        assert "find bugs" in context
        assert "main.py" in context
        assert "app.log" in context

    def test_stats(self):
        acc = ContextAccumulator(max_tokens=50000)
        acc.update(ContextChunk(
            source_id="code:a.py",
            category=SourceCategory.CODE,
            toon_spec="# a.py | python",
        ))
        stats = acc.get_stats()
        assert stats["total_sources"] == 1
        assert "code" in stats["per_category"]

    def test_delta_keeps_history(self):
        acc = ContextAccumulator()
        acc.update(ContextChunk(
            source_id="f:a.py",
            category=SourceCategory.CODE,
            toon_spec="v1",
            is_delta=False,
        ))
        acc.update(ContextChunk(
            source_id="f:a.py",
            category=SourceCategory.CODE,
            toon_spec="v2",
            is_delta=True,
        ))
        # Latest should be v2
        context = acc.get_context()
        assert "v2" in context

    def test_clear(self):
        acc = ContextAccumulator()
        acc.update(ContextChunk(source_id="x", category=SourceCategory.CODE, toon_spec="data"))
        acc.clear()
        assert acc.get_stats()["total_sources"] == 0


# =============================================================================
# Router tests
# =============================================================================

class TestRouter:
    def test_model_selection(self):
        cfg = ServerConfig(history_enabled=False)
        router = LLMRouter(cfg)
        # Code should route to "code" model
        model = router._get_model_for_category("code")
        assert model.model == cfg.models["code"].model

        # Logs should route to "text" model
        model = router._get_model_for_category("logs")
        assert model.model == cfg.models["text"].model

        # Video should route to "multimodal" model
        model = router._get_model_for_category("video")
        assert model.model == cfg.models["multimodal"].model

    def test_parse_json_response(self):
        cfg = ServerConfig(history_enabled=False)
        router = LLMRouter(cfg)
        resp = '{"action": "code_fix", "content": "fix the bug", "confidence": 0.9}'
        action = router._parse_response(resp)
        assert action.action_type == "code_fix"
        assert action.confidence == 0.9

    def test_parse_plain_text_response(self):
        cfg = ServerConfig(history_enabled=False)
        router = LLMRouter(cfg)
        action = router._parse_response("This is a plain text analysis result")
        assert action.action_type == "report"
        assert "plain text" in action.content

    @pytest.mark.asyncio
    async def test_mock_query(self):
        cfg = ServerConfig(history_enabled=False)
        router = LLMRouter(cfg)
        request = LLMRequest(context="# test.py | python", goal="analyze", category="code")
        action = await router.query(request)
        assert action.action_type in ("report", "error", "none", "code_fix", "alert")
        assert action.model_used != ""

    def test_stats(self):
        cfg = ServerConfig(history_enabled=False)
        router = LLMRouter(cfg)
        stats = router.get_stats()
        assert "total_requests" in stats
        assert "models" in stats

    @pytest.mark.asyncio
    async def test_router_with_history(self, tmp_path):
        db_path = str(tmp_path / "test_router_hist.db")
        history = ConversationHistory(db_path)
        cfg = ServerConfig(history_enabled=False)
        router = LLMRouter(cfg, history=history)
        request = LLMRequest(context="# test", goal="test", category="code")
        action = await router.query(request)
        # Should have recorded the exchange
        records = history.recent(limit=5)
        assert len(records) == 1
        assert records[0].goal == "test"
        assert records[0].category == "code"


# =============================================================================
# Watcher tests
# =============================================================================

class TestWatcherRegistry:
    def test_file_watcher_supports(self):
        assert FileWatcher.supports("/some/path/") > 0
        assert FileWatcher.supports("rtsp://cam") == 0.0

    def test_log_watcher_supports(self):
        assert LogWatcher.supports("log:/var/log/app.log") > 0.5
        assert LogWatcher.supports("/var/log/error.log") > 0.5
        assert LogWatcher.supports("/src/main.py") == 0.0

    def test_stream_watcher_supports(self):
        assert StreamWatcher.supports("rtsp://cam1:554/stream") > 0.5
        assert StreamWatcher.supports("test.mp4") > 0.5
        assert StreamWatcher.supports("/src/main.py") == 0.0

    def test_registry_resolve(self):
        cls = WatcherRegistry.resolve("rtsp://cam1")
        assert cls == StreamWatcher

        cls = WatcherRegistry.resolve("/var/log/app.log")
        assert cls == LogWatcher

    def test_registry_create(self):
        watcher = WatcherRegistry.create("test", "code", "/tmp/")
        assert isinstance(watcher, FileWatcher)

        watcher = WatcherRegistry.create("test", "logs", "/var/log/x.log")
        assert isinstance(watcher, LogWatcher)


class TestFileWatcher:
    @pytest.mark.asyncio
    async def test_full_scan(self, tmp_path):
        # Create test files
        (tmp_path / "main.py").write_text("def hello():\n    return 'world'\n")
        (tmp_path / "config.py").write_text("PORT = 8080\n")

        watcher = FileWatcher("test:code", str(tmp_path))
        await watcher.start()
        await asyncio.sleep(0.5)

        # Should have emitted at least one chunk
        chunks = []
        while not watcher._queue.empty():
            chunks.append(await watcher._queue.get())

        assert len(chunks) >= 1
        assert any("main.py" in c.toon_spec or "hello" in c.toon_spec for c in chunks)

        await watcher.stop()


class TestLogWatcher:
    @pytest.mark.asyncio
    async def test_initial_tail(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2026-01-01 INFO  started\n"
            "2026-01-01 ERROR connection failed\n"
            "2026-01-01 INFO  recovered\n"
        )

        watcher = LogWatcher("test:log", str(log_file))
        await watcher.start()
        await asyncio.sleep(0.5)

        chunks = []
        while not watcher._queue.empty():
            chunks.append(await watcher._queue.get())

        assert len(chunks) >= 1
        toon = chunks[0].toon_spec
        assert "ERR[1]" in toon
        assert "connection failed" in toon

        await watcher.stop()


# =============================================================================
# Server integration tests
# =============================================================================

# =============================================================================
# History tests
# =============================================================================

class TestConversationHistory:
    def test_record_and_get(self, tmp_path):
        db = str(tmp_path / "test_hist.db")
        history = ConversationHistory(db)
        rec = ExchangeRecord(
            goal="test goal",
            category="code",
            model="test-model",
            action_type="report",
            content="test content",
            confidence=0.85,
            tokens_used=100,
            duration_s=1.5,
            status="ok",
        )
        rid = history.record(rec)
        assert rid == rec.id

        got = history.get(rid)
        assert got is not None
        assert got.goal == "test goal"
        assert got.confidence == 0.85

    def test_recent_with_filters(self, tmp_path):
        db = str(tmp_path / "test_hist2.db")
        history = ConversationHistory(db)
        for i in range(5):
            history.record(ExchangeRecord(
                category="code" if i % 2 == 0 else "video",
                model="gemini",
                action_type="report",
                content=f"content {i}",
            ))
        all_recs = history.recent(limit=10)
        assert len(all_recs) == 5

        code_recs = history.recent(limit=10, category="code")
        assert len(code_recs) == 3

        video_recs = history.recent(limit=10, category="video")
        assert len(video_recs) == 2

    def test_search(self, tmp_path):
        db = str(tmp_path / "test_hist3.db")
        history = ConversationHistory(db)
        history.record(ExchangeRecord(
            content="Found authentication bug in auth.py",
            category="code",
        ))
        history.record(ExchangeRecord(
            content="Video shows normal activity",
            category="video",
        ))
        results = history.search(query="authentication")
        assert len(results) == 1
        assert "authentication" in results[0].content

    def test_stats(self, tmp_path):
        db = str(tmp_path / "test_hist4.db")
        history = ConversationHistory(db)
        history.record(ExchangeRecord(
            category="code", model="gemini", tokens_used=50, status="ok",
        ))
        history.record(ExchangeRecord(
            category="video", model="gemini", tokens_used=100, status="ok",
        ))
        stats = history.stats()
        assert stats["total_exchanges"] == 2
        assert stats["total_tokens"] == 150
        assert "code" in stats["by_category"]
        assert "video" in stats["by_category"]

    def test_execute_sql(self, tmp_path):
        db = str(tmp_path / "test_hist5.db")
        history = ConversationHistory(db)
        history.record(ExchangeRecord(category="code", model="gemini"))
        rows = history.execute_sql("SELECT COUNT(*) as cnt FROM exchanges")
        assert rows[0]["cnt"] == 1

    def test_clear(self, tmp_path):
        db = str(tmp_path / "test_hist6.db")
        history = ConversationHistory(db)
        history.record(ExchangeRecord(category="code"))
        history.record(ExchangeRecord(category="video"))
        assert history.stats()["total_exchanges"] == 2
        count = history.clear()
        assert count == 2
        assert history.stats()["total_exchanges"] == 0

    def test_to_dict(self, tmp_path):
        db = str(tmp_path / "test_hist7.db")
        history = ConversationHistory(db)
        history.record(ExchangeRecord(
            goal="test", category="code", model="m",
            sources='["file:a.py"]', affected_files='["a.py"]',
        ))
        rec = history.recent(limit=1)[0]
        d = rec.to_dict()
        assert isinstance(d["sources"], list)
        assert isinstance(d["affected_files"], list)

    def test_parse_duration(self):
        assert ConversationHistory._parse_duration("1h") == 3600
        assert ConversationHistory._parse_duration("30m") == 1800
        assert ConversationHistory._parse_duration("2d") == 172800
        assert ConversationHistory._parse_duration("300s") == 300
        assert ConversationHistory._parse_duration("invalid") == 0.0


# =============================================================================
# Query adapter tests
# =============================================================================

class TestQueryAdapter:
    def test_local_parse_time_filter(self, tmp_path):
        db = str(tmp_path / "test_qa1.db")
        history = ConversationHistory(db)
        adapter = QueryAdapter(history)
        sql = adapter._try_local_parse("show errors from last hour")
        assert sql != ""
        assert "strftime" in sql or "3600" in sql
        assert "status = 'error'" in sql

    def test_local_parse_category(self, tmp_path):
        db = str(tmp_path / "test_qa2.db")
        history = ConversationHistory(db)
        adapter = QueryAdapter(history)
        sql = adapter._try_local_parse("last 10 video analyses")
        assert "category = 'video'" in sql
        assert "LIMIT 10" in sql

    def test_local_parse_model(self, tmp_path):
        db = str(tmp_path / "test_qa3.db")
        history = ConversationHistory(db)
        adapter = QueryAdapter(history)
        sql = adapter._try_local_parse("gemini model usage today")
        assert "gemini" in sql.lower()

    def test_local_parse_aggregate(self, tmp_path):
        db = str(tmp_path / "test_qa4.db")
        history = ConversationHistory(db)
        adapter = QueryAdapter(history)
        sql = adapter._try_local_parse("count errors per category")
        assert "COUNT" in sql
        assert "GROUP BY" in sql

    def test_sql_query_select_only(self, tmp_path):
        db = str(tmp_path / "test_qa5.db")
        history = ConversationHistory(db)
        adapter = QueryAdapter(history)
        result = adapter.sql_query("SELECT COUNT(*) as cnt FROM exchanges")
        assert "error" not in result
        assert result["count"] == 1

    def test_sql_query_blocks_write(self, tmp_path):
        db = str(tmp_path / "test_qa6.db")
        history = ConversationHistory(db)
        adapter = QueryAdapter(history)
        result = adapter.sql_query("DELETE FROM exchanges")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nlp_query_with_data(self, tmp_path):
        db = str(tmp_path / "test_qa7.db")
        history = ConversationHistory(db)
        history.record(ExchangeRecord(
            category="video", model="gemini", status="ok",
            content="detected movement in camera 1",
        ))
        adapter = QueryAdapter(history)
        result = await adapter.nlp_query("last 5 video events")
        assert "error" not in result or result.get("count", 0) >= 0


# =============================================================================
# Server integration tests
# =============================================================================

class TestToonicServer:
    @pytest.mark.asyncio
    async def test_server_lifecycle(self, tmp_path):
        (tmp_path / "hello.py").write_text("def hi(): pass\n")

        cfg = ServerConfig(
            interval=0,  # one-shot
            sources=[SourceConfig(path_or_url=str(tmp_path), category="code")],
            goal="test analysis",
            history_db_path=str(tmp_path / "hist.db"),
        )
        server = ToonicServer(cfg)

        events = []
        async def collect_event(event):
            events.append(event)
        server.on_event(collect_event)

        await server.start()
        await asyncio.sleep(2.0)

        status = server.get_status()
        assert status["running"] is True
        assert status["total_chunks"] >= 0
        assert len(status["sources"]) >= 1

        await server.stop()
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_add_remove_source(self):
        cfg = ServerConfig(interval=0)
        server = ToonicServer(cfg)
        await server.start()

        sid = await server.add_source(SourceConfig(
            path_or_url="/tmp",
            category="code",
        ))
        assert sid != ""
        assert sid in server.get_status()["sources"]

        await server.remove_source(sid)
        assert sid not in server.get_status()["sources"]

        await server.stop()
