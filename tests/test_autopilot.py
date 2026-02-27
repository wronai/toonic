"""
Tests for toonic.autopilot — scaffold, executor, prompts, loop.
"""

from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path

from toonic.autopilot.scaffold import ProjectScaffold, ProjectSpec
from toonic.autopilot.executor import ActionExecutor, ExecutionResult
from toonic.autopilot.prompts import AutopilotPrompt, ScaffoldPrompt, FixPrompt
from toonic.server.models import ContextChunk, SourceCategory


# ── Scaffold Tests ───────────────────────────────────────────────────


class TestProjectScaffold:
    def test_detect_spec_api(self):
        spec = ProjectScaffold.detect_spec("REST API for task management")
        assert spec.project_type == "api"
        assert spec.language == "python"

    def test_detect_spec_cli(self):
        spec = ProjectScaffold.detect_spec("CLI tool for word counting")
        assert spec.project_type == "cli"
        assert spec.language == "python"

    def test_detect_spec_pipeline(self):
        spec = ProjectScaffold.detect_spec("Data pipeline for CSV transformation")
        assert spec.project_type == "data-pipeline"

    def test_detect_spec_javascript(self):
        spec = ProjectScaffold.detect_spec("Express.js REST API for users")
        assert spec.language == "javascript"
        assert spec.project_type == "api"

    def test_detect_spec_name(self):
        spec = ProjectScaffold.detect_spec("Something cool", name="my-project")
        assert spec.name == "my-project"

    def test_detect_spec_auto_name(self):
        spec = ProjectScaffold.detect_spec("REST API for books")
        assert spec.name  # should auto-generate

    def test_generate_python_api(self, tmp_path):
        spec = ProjectSpec(
            name="test-api",
            description="Test API",
            language="python",
            project_type="api",
            dependencies=["fastapi>=0.110"],
        )
        files = ProjectScaffold.generate(spec, tmp_path)
        assert "pyproject.toml" in files
        assert "test_api/__init__.py" in files
        assert "test_api/api.py" in files
        assert "tests/test_test_api.py" in files
        assert "project.toon" in files
        assert "ROADMAP.md" in files
        assert "README.md" in files

    def test_generate_python_cli(self, tmp_path):
        spec = ProjectSpec(
            name="my-tool",
            description="A CLI tool",
            language="python",
            project_type="cli",
        )
        files = ProjectScaffold.generate(spec, tmp_path)
        assert "my_tool/cli.py" in files
        assert "my_tool/models.py" in files

    def test_generate_javascript(self, tmp_path):
        spec = ProjectSpec(
            name="js-api",
            description="JS API",
            language="javascript",
            project_type="api",
        )
        files = ProjectScaffold.generate(spec, tmp_path)
        assert "package.json" in files
        assert "src/index.js" in files

    def test_init_creates_dir(self, tmp_path):
        out = tmp_path / "new-project"
        spec, files = ProjectScaffold.init(
            "REST API for todos", name="todo-api", output_dir=str(out)
        )
        assert spec.name == "todo-api"
        assert out.exists()
        assert (out / "project.toon").exists()
        assert (out / "ROADMAP.md").exists()
        assert len(files) >= 8

    def test_project_toon_content(self, tmp_path):
        spec, files = ProjectScaffold.init(
            "CLI tool for parsing", name="parser", output_dir=str(tmp_path / "p")
        )
        toon = files.get("project.toon", "")
        assert "parser" in toon
        assert "cli" in toon.lower()

    def test_roadmap_has_phases(self, tmp_path):
        spec, files = ProjectScaffold.init(
            "REST API", name="api", output_dir=str(tmp_path / "a")
        )
        roadmap = files.get("ROADMAP.md", "")
        assert "Phase 1" in roadmap
        assert "Phase 2" in roadmap
        assert "- [ ]" in roadmap


# ── Executor Tests ───────────────────────────────────────────────────


class TestActionExecutor:
    def test_execute_files_array(self, tmp_path):
        executor = ActionExecutor(project_dir=tmp_path)
        action = {
            "action": "implement",
            "files": [
                {"path": "hello.py", "content": "print('hello')"},
                {"path": "lib/utils.py", "content": "def add(a, b): return a + b"},
            ],
        }
        result = executor.execute(action)
        assert result.success
        assert len(result.files_written) == 2
        assert (tmp_path / "hello.py").read_text() == "print('hello')"
        assert (tmp_path / "lib" / "utils.py").exists()

    def test_execute_target_path(self, tmp_path):
        executor = ActionExecutor(project_dir=tmp_path)
        action = {
            "action_type": "code_fix",
            "target_path": "main.py",
            "content": "```python\nprint('fixed')\n```",
        }
        result = executor.execute(action)
        assert result.success
        assert (tmp_path / "main.py").read_text() == "print('fixed')"

    def test_execute_dry_run(self, tmp_path):
        executor = ActionExecutor(project_dir=tmp_path, dry_run=True)
        action = {
            "action": "implement",
            "files": [{"path": "x.py", "content": "pass"}],
        }
        result = executor.execute(action)
        assert result.success
        assert not (tmp_path / "x.py").exists()  # dry-run: no file written

    def test_execute_report(self, tmp_path):
        executor = ActionExecutor(project_dir=tmp_path)
        result = executor.execute({"action_type": "report", "content": "looks good"})
        assert result.success
        assert result.action_type == "report"

    def test_execute_none(self, tmp_path):
        executor = ActionExecutor(project_dir=tmp_path)
        result = executor.execute({"action_type": "none"})
        assert result.success

    def test_path_traversal_blocked(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        executor = ActionExecutor(project_dir=project)
        # This path resolves outside project_dir
        action = {
            "action": "implement",
            "files": [{"path": "../../../tmp/evil.py", "content": "hacked"}],
        }
        result = executor.execute(action)
        # Should not write outside project dir
        assert not (tmp_path / "tmp" / "evil.py").exists()

    def test_extract_code_block(self):
        text = "Here's the fix:\n```python\nprint('hello')\n```\nDone."
        code = ActionExecutor._extract_code(text)
        assert code == "print('hello')"

    def test_extract_code_raw(self):
        text = "import os\ndef main(): pass"
        code = ActionExecutor._extract_code(text)
        assert "import os" in code

    def test_extract_file_blocks(self):
        text = "```task_api/models.py\nclass Task: pass\n```\n\n```tests/test.py\ndef test(): pass\n```"
        blocks = ActionExecutor._extract_file_blocks(text)
        assert "task_api/models.py" in blocks
        assert "tests/test.py" in blocks

    def test_history(self, tmp_path):
        executor = ActionExecutor(project_dir=tmp_path)
        executor.execute({"action_type": "report", "content": "test"})
        history = executor.get_history()
        assert len(history) == 1
        assert history[0]["action_type"] == "report"

    def test_delete_file(self, tmp_path):
        (tmp_path / "to_delete.py").write_text("old code")
        executor = ActionExecutor(project_dir=tmp_path)
        result = executor.execute({
            "action_type": "delete_file",
            "target_path": "to_delete.py",
        })
        assert result.success
        assert not (tmp_path / "to_delete.py").exists()


# ── Prompt Tests ─────────────────────────────────────────────────────


class TestAutopilotPrompt:
    def test_build_basic(self):
        prompt = AutopilotPrompt()
        result = prompt.build(
            goal="build MVP",
            chunks=[ContextChunk(source_id="main.py", category=SourceCategory.CODE, toon_spec="def main(): pass")],
            images=[],
        )
        assert "system" in result
        assert "user" in result
        assert "build MVP" in result["user"]
        assert "Autopilot" in result["system"]

    def test_build_with_roadmap(self):
        prompt = AutopilotPrompt()
        result = prompt.build(
            goal="build MVP",
            chunks=[],
            images=[],
            roadmap="- [ ] Task 1\n- [ ] Task 2",
        )
        assert "Task 1" in result["user"]

    def test_build_with_test_output(self):
        prompt = AutopilotPrompt()
        result = prompt.build(
            goal="fix bugs",
            chunks=[],
            images=[],
            test_output="FAILED test_foo - assert False",
        )
        assert "FAILED" in result["user"]

    def test_build_with_iteration(self):
        prompt = AutopilotPrompt()
        result = prompt.build(
            goal="build", chunks=[], images=[], iteration=5
        )
        assert "Iteration #5" in result["user"]


class TestScaffoldPrompt:
    def test_build(self):
        prompt = ScaffoldPrompt()
        result = prompt.build(
            description="REST API for books",
            name="bookstore",
            language="python",
            project_type="api",
        )
        assert "bookstore" in result["user"]
        assert "python" in result["user"].lower()


class TestFixPrompt:
    def test_build(self):
        prompt = FixPrompt()
        chunk = ContextChunk(
            source_id="main.py", category=SourceCategory.CODE,
            toon_spec="def foo(): return 1",
        )
        result = prompt.build(
            goal="fix tests",
            test_output="FAILED test_foo\nassert 1 == 2",
            chunks=[chunk],
        )
        assert "FAILED" in result["user"]
        assert "ROOT CAUSE" in result["system"]


# ── Parser Tests ─────────────────────────────────────────────────────


class TestParserRawToDict:
    def test_parse_json_fenced(self):
        from toonic.server.llm.parser import ResponseParser
        parser = ResponseParser()
        content = '```json\n{"action": "implement", "files": []}\n```'
        result = parser.parse_raw_to_dict(content)
        assert result is not None
        assert result["action"] == "implement"

    def test_parse_json_with_preamble(self):
        from toonic.server.llm.parser import ResponseParser
        parser = ResponseParser()
        content = 'Here is the result:\n{"action": "report", "content": "all good"}'
        result = parser.parse_raw_to_dict(content)
        assert result is not None
        assert result["action"] == "report"

    def test_parse_nested_json(self):
        from toonic.server.llm.parser import ResponseParser
        parser = ResponseParser()
        content = json.dumps({
            "action": "implement",
            "files": [{"path": "a.py", "content": "x = {'key': 'val'}"}],
        })
        result = parser.parse_raw_to_dict(content)
        assert result is not None
        assert len(result["files"]) == 1

    def test_parse_empty(self):
        from toonic.server.llm.parser import ResponseParser
        parser = ResponseParser()
        assert parser.parse_raw_to_dict("") is None
        assert parser.parse_raw_to_dict("no json here") is None

    def test_parse_trailing_comma(self):
        from toonic.server.llm.parser import ResponseParser
        parser = ResponseParser()
        content = '{"action": "report", "content": "test",}'
        result = parser.parse_raw_to_dict(content)
        assert result is not None
        assert result["action"] == "report"
