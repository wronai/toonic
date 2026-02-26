"""
Tests for toonic.core — Stage 0: Foundation
"""

import pytest
from pathlib import Path

from toonic.core import (
    FileLogic,
    FileHandler,
    BaseHandlerMixin,
    FormatRegistry,
    SpecDetector,
    CodeLogicBase,
)


class TestFormatRegistry:
    """Tests for FormatRegistry."""

    def test_register_and_resolve(self):
        FormatRegistry.reset()

        class MockHandler:
            extensions = frozenset({'.test'})
            category = 'test'
            requires = ()
            def parse(self, path): return None
            def to_spec(self, logic, fmt): return ""
            def reproduce(self, logic, client, target_fmt): return ""
            def sniff(self, path, content): return 0.5

        handler = MockHandler()
        FormatRegistry.register(handler)
        resolved = FormatRegistry.resolve(Path("file.test"))
        assert resolved is handler

    def test_available(self):
        FormatRegistry.reset()

        class MockHandler:
            extensions = frozenset({'.test'})
            category = 'test'
            requires = ()
            def parse(self, path): return None
            def to_spec(self, logic, fmt): return ""
            def reproduce(self, logic, client, target_fmt): return ""
            def sniff(self, path, content): return 0.5

        FormatRegistry.register(MockHandler())
        avail = FormatRegistry.available()
        assert len(avail) == 1

    def test_list_categories(self):
        FormatRegistry.reset()

        class MockHandler:
            extensions = frozenset({'.test'})
            category = 'mycat'
            requires = ()
            def parse(self, path): return None
            def to_spec(self, logic, fmt): return ""
            def reproduce(self, logic, client, target_fmt): return ""
            def sniff(self, path, content): return 0.5

        FormatRegistry.register(MockHandler())
        cats = FormatRegistry.list_categories()
        assert 'mycat' in cats
        assert '.test' in cats['mycat']

    def test_resolve_none_for_unknown(self):
        FormatRegistry.reset()
        assert FormatRegistry.resolve(Path("file.xyz")) is None

    def test_content_sniffing_disambiguation(self):
        """When multiple handlers match same extension, sniff() picks the best."""
        FormatRegistry.reset()

        class HandlerA:
            extensions = frozenset({'.yaml'})
            category = 'a'
            requires = ()
            def parse(self, path): return None
            def to_spec(self, logic, fmt): return ""
            def reproduce(self, logic, client, target_fmt): return ""
            def sniff(self, path, content): return 0.3

        class HandlerB:
            extensions = frozenset({'.yaml'})
            category = 'b'
            requires = ()
            def parse(self, path): return None
            def to_spec(self, logic, fmt): return ""
            def reproduce(self, logic, client, target_fmt): return ""
            def sniff(self, path, content): return 0.9

        FormatRegistry.register(HandlerA())
        FormatRegistry.register(HandlerB())

        resolved = FormatRegistry.resolve(Path("test.yaml"), content="some content")
        assert resolved.category == 'b'


class TestSpecDetector:
    """Tests for SpecDetector."""

    def test_detect_code(self):
        assert SpecDetector.detect("# myproject | 42f | python:35") == 'code'

    def test_detect_document(self):
        assert SpecDetector.detect("# README.md | markdown | 1240w") == 'document'

    def test_detect_database(self):
        assert SpecDetector.detect("# schema.sql | postgresql | 6 tables") == 'database'

    def test_detect_infra(self):
        assert SpecDetector.detect("# deploy.yaml | kubernetes | 3 resources") == 'infra'

    def test_detect_api(self):
        assert SpecDetector.detect("# api.yaml | openapi 3.0 | 12 endpoints") == 'api'

    def test_detect_data(self):
        assert SpecDetector.detect("# data.csv | csv | 1250 rows") == 'data'

    def test_detect_config(self):
        assert SpecDetector.detect("# Dockerfile | dockerfile | 12 instructions") == 'config'

    def test_detect_unknown(self):
        assert SpecDetector.detect("random content here") == 'unknown'

    def test_detect_spec_format_json(self):
        assert SpecDetector.detect_spec_format('{"key": "val"}') == 'json'

    def test_detect_spec_format_toon(self):
        assert SpecDetector.detect_spec_format('# proj | M[42]:\n  mod.py') == 'toon'

    def test_detect_spec_format_yaml(self):
        assert SpecDetector.detect_spec_format('source_file: test.py') == 'yaml'

    def test_detect_heuristic_database(self):
        content = "T[3]:\n  users | id:bigserial PK, email:varchar FK→profiles"
        assert SpecDetector.detect(content) == 'database'

    def test_detect_heuristic_code(self):
        content = "M[10]:\n  main.py,100\n    f[3]: foo,bar"
        assert SpecDetector.detect(content) == 'code'


class TestCodeLogicBase:
    """Tests for CodeLogicBase."""

    def test_to_dict(self):
        logic = CodeLogicBase(
            source_file="test.py",
            source_hash="abc123",
            lines=100,
            functions=[{"name": "foo", "sig": "() -> None"}],
            classes=[{"name": "Bar"}],
        )
        d = logic.to_dict()
        assert d["source_file"] == "test.py"
        assert len(d["functions"]) == 1
        assert len(d["classes"]) == 1

    def test_complexity(self):
        logic = CodeLogicBase(
            source_file="test.py",
            source_hash="abc123",
            lines=100,
            functions=[{"name": "foo"}],
            classes=[{"name": "Bar"}],
        )
        assert logic.complexity() == 3 + 1 + 1  # 1 class*3 + 1 func + 100//100


class TestBaseHandlerMixin:
    """Tests for BaseHandlerMixin."""

    def test_format_toon_header(self):
        mixin = BaseHandlerMixin()
        header = mixin._format_toon_header("test.py", "python", lines=100, classes=3)
        assert "# test.py" in header
        assert "python" in header
        assert "lines:100" in header
        assert "classes:3" in header
