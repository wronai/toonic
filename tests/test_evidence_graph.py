"""
Tests for toonic.formats.evidence — Stage 7: Evidence Graph
"""

import pytest

from toonic.formats.evidence import (
    EvidenceNode,
    EvidenceGraph,
    EvidenceGraphBuilder,
    EvidenceGraphHandler,
)
from toonic.core.registry import FormatRegistry


class TestEvidenceNode:
    def test_create(self):
        node = EvidenceNode(
            id="code:auth.py:validate_token",
            category="code",
            summary="validate_token(token:str)->bool",
            source_path="auth.py",
        )
        assert node.category == "code"
        assert node.confidence == 1.0


class TestEvidenceGraphBuilder:
    def test_add_code_evidence(self):
        builder = EvidenceGraphBuilder()
        builder.add_code_evidence("auth.py", [
            {"name": "validate_token", "sig": "(token:str)->bool"},
            {"name": "create_session", "sig": "(user:User)->Session"},
        ])
        assert len(builder.nodes) == 2

    def test_add_document_evidence(self):
        builder = EvidenceGraphBuilder()
        builder.add_document_evidence("README.md", [
            {"title": "Installation", "summary": "pip install toonic"},
        ])
        assert len(builder.nodes) == 1
        assert builder.nodes[0].category == 'document'

    def test_add_video_evidence(self):
        builder = EvidenceGraphBuilder()
        builder.add_video_evidence("cam1.mp4", [
            {"ts": 5.2, "score": 0.45, "b64": "AAAA", "size": 2500},
        ])
        assert len(builder.nodes) == 1
        assert builder.nodes[0].category == 'video'

    def test_add_audio_evidence(self):
        builder = EvidenceGraphBuilder()
        builder.add_audio_evidence("meeting.wav", [
            {"start": 12.3, "duration": 2.8, "b64": "CCCC", "size": 11200},
        ])
        assert len(builder.nodes) == 1
        assert builder.nodes[0].category == 'audio'

    def test_add_database_evidence(self):
        builder = EvidenceGraphBuilder()
        builder.add_database_evidence("schema.sql", [
            {"name": "users", "columns": [{"name": "id"}, {"name": "email"}]},
        ])
        assert len(builder.nodes) == 1
        assert builder.nodes[0].category == 'database'

    def test_add_test_evidence(self):
        builder = EvidenceGraphBuilder()
        builder.add_test_evidence("test_report.xml", {
            "total": 120, "passed": 115, "failed": 5,
        })
        assert len(builder.nodes) == 1
        assert builder.nodes[0].category == 'test'

    def test_build_full_graph(self):
        builder = EvidenceGraphBuilder()
        builder.add_code_evidence("auth.py", [
            {"name": "validate_token", "sig": "(token:str)->bool"},
            {"name": "create_session", "sig": "(user:User)->Session"},
        ])
        builder.add_document_evidence("README.md", [
            {"title": "Installation", "summary": "pip install toonic"},
            {"title": "Usage", "summary": "Run code2logic spec ./"},
        ])
        builder.add_video_evidence("cam1.mp4", [
            {"ts": 5.2, "score": 0.45, "b64": "AAAA", "size": 2500},
            {"ts": 23.1, "score": 0.67, "b64": "BBBB", "size": 2300},
        ])
        builder.add_audio_evidence("meeting.wav", [
            {"start": 12.3, "duration": 2.8, "b64": "CCCC", "size": 11200},
            {"start": 45.6, "duration": 6.4, "b64": "DDDD", "size": 25600},
        ])
        builder.add_database_evidence("schema.sql", [
            {"name": "users", "columns": [{"name": "id"}, {"name": "email"}]},
            {"name": "posts", "columns": [{"name": "id"}, {"name": "title"}]},
        ])
        builder.add_test_evidence("test_report.xml", {
            "total": 120, "passed": 115, "failed": 5,
        })

        eg = builder.build(title="Project Analysis")
        assert eg.num_sources == 6
        assert len(eg.nodes) == 11
        assert 'code' in eg.category_stats
        assert 'video' in eg.category_stats
        assert 'audio' in eg.category_stats
        assert 'database' in eg.category_stats
        assert 'test' in eg.category_stats

    def test_toon_generation(self):
        builder = EvidenceGraphBuilder()
        builder.add_code_evidence("auth.py", [{"name": "validate_token"}])
        builder.add_video_evidence("cam.mp4", [{"ts": 5.0, "score": 0.5, "b64": "", "size": 100}])
        builder.add_audio_evidence("audio.wav", [{"start": 3.0, "duration": 1.0, "b64": "", "size": 50}])
        builder.add_database_evidence("db.sql", [{"name": "users", "columns": []}])
        builder.add_test_evidence("tests.xml", {"total": 10, "passed": 9, "failed": 1})

        eg = builder.build()
        handler = EvidenceGraphHandler()
        toon = handler.to_spec(eg, 'toon')

        assert '[CODE]' in toon
        assert '[VIDEO]' in toon
        assert '[AUDIO]' in toon
        assert '[DATABASE]' in toon
        assert '[TEST]' in toon

    def test_auto_link_same_source(self):
        builder = EvidenceGraphBuilder()
        builder.add_code_evidence("auth.py", [
            {"name": "func_a"},
            {"name": "func_b"},
        ])
        eg = builder.build()

        node_a = eg.nodes[0]
        node_b = eg.nodes[1]
        assert node_b.id in node_a.related_to
        assert node_a.id in node_b.related_to

    def test_to_dict(self):
        builder = EvidenceGraphBuilder()
        builder.add_code_evidence("auth.py", [{"name": "fn"}])
        eg = builder.build()

        d = eg.to_dict()
        assert d["total_nodes"] == 1
        assert "code" in d["categories"]
