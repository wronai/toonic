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
        cfg = ServerConfig()
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
        cfg = ServerConfig()
        router = LLMRouter(cfg)
        resp = '{"action": "code_fix", "content": "fix the bug", "confidence": 0.9}'
        action = router._parse_response(resp)
        assert action.action_type == "code_fix"
        assert action.confidence == 0.9

    def test_parse_plain_text_response(self):
        cfg = ServerConfig()
        router = LLMRouter(cfg)
        action = router._parse_response("This is a plain text analysis result")
        assert action.action_type == "report"
        assert "plain text" in action.content

    @pytest.mark.asyncio
    async def test_mock_query(self):
        cfg = ServerConfig()
        router = LLMRouter(cfg)
        request = LLMRequest(context="# test.py | python", goal="analyze", category="code")
        action = await router.query(request)
        # Should return mock response (litellm not installed in test env)
        assert action.action_type in ("report", "error")
        assert action.model_used != ""

    def test_stats(self):
        cfg = ServerConfig()
        router = LLMRouter(cfg)
        stats = router.get_stats()
        assert "total_requests" in stats
        assert "models" in stats


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

class TestToonicServer:
    @pytest.mark.asyncio
    async def test_server_lifecycle(self, tmp_path):
        (tmp_path / "hello.py").write_text("def hi(): pass\n")

        cfg = ServerConfig(
            interval=0,  # one-shot
            sources=[SourceConfig(path_or_url=str(tmp_path), category="code")],
            goal="test analysis",
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
