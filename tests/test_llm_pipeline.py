"""
Tests for the refactored LLM pipeline components.

Covers: PromptBuilders, ResponseParser, Accumulator priority eviction,
        template loading, ContentType/priority on models.
"""

import pytest
from pathlib import Path

from toonic.server.models import ContextChunk, ContentType, SourceCategory, ActionResponse
from toonic.server.llm.prompts import (
    GenericPrompt, CodeAnalysisPrompt, CCTVEventPrompt, select_prompt_builder,
)
from toonic.server.llm.parser import ResponseParser
from toonic.server.core.accumulator import ContextAccumulator, BudgetConfig


# =============================================================================
# Prompt Builders
# =============================================================================

class TestGenericPrompt:
    def test_includes_goal(self):
        builder = GenericPrompt()
        result = builder.build(
            goal="analyze this",
            chunks=[ContextChunk(source_id="test", category=SourceCategory.CODE, toon_spec="hello")],
            images=[],
        )
        assert "analyze this" in result["user"]
        assert "system" in result
        assert result["images"] == []

    def test_includes_chunk_content(self):
        builder = GenericPrompt()
        result = builder.build(
            goal="test",
            chunks=[ContextChunk(source_id="main.py", category=SourceCategory.CODE, toon_spec="# main.py | python")],
            images=[],
        )
        assert "main.py" in result["user"]
        assert "[code]" in result["user"]

    def test_with_images(self):
        builder = GenericPrompt()
        result = builder.build(
            goal="test",
            chunks=[],
            images=["base64data1", "base64data2"],
        )
        assert len(result["images"]) == 2
        assert "2 images attached" in result["user"]


class TestCodeAnalysisPrompt:
    def test_uses_toon_instruction(self):
        builder = CodeAnalysisPrompt()
        result = builder.build(
            goal="find bugs",
            chunks=[ContextChunk(
                source_id="main.py", category=SourceCategory.CODE,
                toon_spec="# main.py | python:45\nM[1]: main.py,45",
            )],
            images=[],
        )
        assert "TOON" in result["system"]
        assert "find bugs" in result["user"]
        assert "main.py" in result["user"]

    def test_separates_code_and_logs(self):
        builder = CodeAnalysisPrompt()
        result = builder.build(
            goal="analyze",
            chunks=[
                ContextChunk(source_id="main.py", category=SourceCategory.CODE, toon_spec="code here"),
                ContextChunk(source_id="app.log", category=SourceCategory.LOGS, toon_spec="[ERR] fail"),
            ],
            images=[],
        )
        assert "Source code" in result["user"]
        assert "Recent logs" in result["user"]

    def test_no_images_in_code_analysis(self):
        builder = CodeAnalysisPrompt()
        result = builder.build(goal="test", chunks=[], images=[])
        assert result["images"] == []


class TestCCTVEventPrompt:
    def test_forbids_scene_description(self):
        builder = CCTVEventPrompt()
        result = builder.build(
            goal="security monitoring",
            chunks=[ContextChunk(
                source_id="cam:entrance", category=SourceCategory.VIDEO,
                toon_spec="", metadata={"detected_objects": [
                    {"label": "person", "confidence": 0.87},
                ]},
            )],
            images=["base64_frame1", "base64_frame2"],
        )
        assert "Do NOT describe" in result["system"]
        assert "EVENT" in result["system"]
        assert "person" in result["user"]
        assert len(result["images"]) == 2

    def test_no_detections(self):
        builder = CCTVEventPrompt()
        result = builder.build(
            goal="monitor",
            chunks=[ContextChunk(source_id="cam1", category=SourceCategory.VIDEO, toon_spec="")],
            images=["frame1"],
        )
        assert "1 attached frames" in result["user"]


class TestSelectPromptBuilder:
    def test_cctv(self):
        builder = select_prompt_builder("CCTV security monitoring", {SourceCategory.VIDEO})
        assert isinstance(builder, CCTVEventPrompt)

    def test_code(self):
        builder = select_prompt_builder("find bugs in code", {SourceCategory.CODE})
        assert isinstance(builder, CodeAnalysisPrompt)

    def test_generic(self):
        builder = select_prompt_builder("analyze data", {SourceCategory.DATA})
        assert isinstance(builder, GenericPrompt)

    def test_config_triggers_code(self):
        builder = select_prompt_builder("review config", {SourceCategory.CONFIG})
        assert isinstance(builder, CodeAnalysisPrompt)


# =============================================================================
# Response Parser
# =============================================================================

class TestResponseParser:
    def test_parse_valid_json(self):
        parser = ResponseParser()
        result = parser.parse({
            "content": '{"action":"report","content":"all good","confidence":0.9}',
            "model": "test-model",
            "tokens_used": 100,
        })
        assert result.action_type == "report"
        assert result.confidence == 0.9
        assert result.tokens_used == 100

    def test_parse_json_in_markdown_fence(self):
        parser = ResponseParser()
        result = parser.parse({
            "content": '```json\n{"action":"code_fix","confidence":0.8}\n```',
            "model": "test",
            "tokens_used": 50,
        })
        assert result.action_type == "code_fix"

    def test_parse_plain_text_fallback(self):
        parser = ResponseParser()
        result = parser.parse({
            "content": "This is a plain text response.",
            "model": "test",
            "tokens_used": 20,
        })
        assert result.action_type == "report"
        assert result.confidence == 0.3
        assert "plain text" in result.content

    def test_parse_error(self):
        parser = ResponseParser()
        result = parser.parse({"error": "timeout", "model": "test", "tokens_used": 0})
        assert result.action_type == "error"
        assert "timeout" in result.content

    def test_parse_preserves_duration(self):
        parser = ResponseParser()
        result = parser.parse({
            "content": '{"action":"report","confidence":0.5}',
            "model": "m", "tokens_used": 10, "duration_s": 2.5,
        })
        assert result.duration_s == 2.5

    def test_parse_action_type_alias(self):
        """Test that 'action_type' key also works (not just 'action')."""
        parser = ResponseParser()
        result = parser.parse({
            "content": '{"action_type":"alert","confidence":0.7}',
            "model": "m", "tokens_used": 10,
        })
        assert result.action_type == "alert"


# =============================================================================
# Accumulator Priority Eviction
# =============================================================================

class TestAccumulatorPriority:
    def test_high_priority_survives_eviction(self):
        # Budget allows ~375 tokens for logs (500 * 0.75), each chunk ~267 tokens
        # So only one chunk fits — the higher-priority one should survive
        acc = ContextAccumulator(config=BudgetConfig(total_tokens=500, allocations={"logs": 0.75}))

        # Low-priority DEBUG — will be evicted
        acc.update(ContextChunk(
            source_id="log1", category=SourceCategory.LOGS,
            toon_spec="x " * 200, priority=0.1,
            content_type=ContentType.LOG_ENTRIES,
        ))
        # High-priority ERROR — should survive
        acc.update(ContextChunk(
            source_id="log2", category=SourceCategory.LOGS,
            toon_spec="y " * 200, priority=0.9,
            content_type=ContentType.LOG_ENTRIES,
        ))

        chunks, _ = acc.get_chunks()
        source_ids = [c.source_id for c in chunks]
        assert "log2" in source_ids

    def test_get_stats_shows_utilization(self):
        acc = ContextAccumulator(config=BudgetConfig(total_tokens=10000, allocations={"code": 0.5}))
        acc.update(ContextChunk(
            source_id="test", category=SourceCategory.CODE, toon_spec="hello world",
        ))
        stats = acc.get_stats()
        assert "code" in stats["per_category"]
        assert stats["per_category"]["code"]["sources"] == 1

    def test_backward_compat_get_context(self):
        acc = ContextAccumulator(max_tokens=10000)
        acc.update(ContextChunk(
            source_id="src", category=SourceCategory.CODE, toon_spec="# test.py | python",
        ))
        ctx = acc.get_context(goal="analyze")
        assert "[GOAL]" in ctx
        assert "test.py" in ctx

    def test_clear_by_category(self):
        acc = ContextAccumulator(max_tokens=10000)
        acc.update(ContextChunk(source_id="s1", category=SourceCategory.CODE, toon_spec="code"))
        acc.update(ContextChunk(source_id="s2", category=SourceCategory.LOGS, toon_spec="log"))
        acc.clear("code")
        stats = acc.get_stats()
        assert "code" not in stats["per_category"]
        assert "logs" in stats["per_category"]


# =============================================================================
# ContentType + Priority on models
# =============================================================================

class TestContentTypeModel:
    def test_default_values(self):
        chunk = ContextChunk(source_id="test", category=SourceCategory.CODE, toon_spec="x")
        assert chunk.content_type == ContentType.RAW_TEXT
        assert chunk.priority == 0.5

    def test_custom_priority(self):
        chunk = ContextChunk(
            source_id="test", category=SourceCategory.LOGS,
            toon_spec="error", priority=0.9, content_type=ContentType.LOG_ENTRIES,
        )
        assert chunk.priority == 0.9
        assert chunk.content_type == ContentType.LOG_ENTRIES

    def test_content_type_enum_values(self):
        assert ContentType.VIDEO_EVENT.value == "video_event"
        assert ContentType.VIDEO_HEARTBEAT.value == "video_heartbeat"
        assert ContentType.LOG_ENTRIES.value == "log_entries"


# =============================================================================
# Template loading
# =============================================================================

class TestTemplateLoading:
    def test_web_ui_template_exists(self):
        template_dir = Path(__file__).parent.parent / "toonic" / "server" / "transport" / "templates"
        assert (template_dir / "web_ui.html").exists()

    def test_events_viewer_template_exists(self):
        template_dir = Path(__file__).parent.parent / "toonic" / "server" / "transport" / "templates"
        assert (template_dir / "events_viewer.html").exists()

    def test_web_ui_has_doctype(self):
        template_dir = Path(__file__).parent.parent / "toonic" / "server" / "transport" / "templates"
        content = (template_dir / "web_ui.html").read_text()
        assert "<!DOCTYPE html>" in content

    def test_load_template_fallback(self):
        from toonic.server.transport.rest_api import _load_template
        result = _load_template("nonexistent.html")
        assert "not found" in result
