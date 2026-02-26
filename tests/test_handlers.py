"""
Tests for toonic.formats — Stages 1-3: Document, Data, Config, API, Infra handlers
"""

import json
import pytest
from pathlib import Path

from toonic.core.registry import FormatRegistry
from toonic.formats.document import MarkdownHandler, TextHandler, RstHandler, DocumentLogic
from toonic.formats.data import CsvHandler, JsonDataHandler, TableLogic, JsonSchemaLogic
from toonic.formats.config import DockerfileHandler, EnvHandler, ConfigLogic
from toonic.formats.database import SqlHandler, SqlSchemaLogic
from toonic.formats.api import OpenApiHandler, ApiLogic
from toonic.formats.infra import KubernetesHandler, GithubActionsHandler, InfraLogic


# =============================================================================
# Stage 1: Document Handlers
# =============================================================================

class TestMarkdownHandler:
    def test_resolve(self, tmp_md):
        handler = FormatRegistry.resolve(tmp_md)
        assert isinstance(handler, MarkdownHandler)

    def test_parse(self, tmp_md):
        handler = MarkdownHandler()
        logic = handler.parse(tmp_md)
        assert logic.title == "Test Document"
        assert logic.source_type == "markdown"
        assert logic.language == "pl"
        assert len(logic.sections) >= 3

    def test_to_toon(self, tmp_md):
        handler = MarkdownHandler()
        logic = handler.parse(tmp_md)
        toon = handler.to_spec(logic, 'toon')
        assert 'D[' in toon
        assert 'markdown' in toon

    def test_to_yaml(self, tmp_md):
        handler = MarkdownHandler()
        logic = handler.parse(tmp_md)
        yaml_spec = handler.to_spec(logic, 'yaml')
        assert 'title:' in yaml_spec
        assert 'sections:' in yaml_spec

    def test_to_json(self, tmp_md):
        handler = MarkdownHandler()
        logic = handler.parse(tmp_md)
        json_spec = handler.to_spec(logic, 'json')
        data = json.loads(json_spec)
        assert data["title"] == "Test Document"

    def test_reproduce_template(self, tmp_md):
        handler = MarkdownHandler()
        logic = handler.parse(tmp_md)
        reproduced = handler.reproduce(logic)
        assert 'Introduction' in reproduced or 'Installation' in reproduced

    def test_sniff(self):
        handler = MarkdownHandler()
        md_content = "# Hello\n\nSome text with [links](http://example.com)\n```python\ncode\n```"
        assert handler.sniff(Path("test.md"), md_content) > 0.5

    def test_complexity(self, tmp_md):
        handler = MarkdownHandler()
        logic = handler.parse(tmp_md)
        assert logic.complexity() > 0


class TestTextHandler:
    def test_parse(self, tmp_txt):
        handler = TextHandler()
        logic = handler.parse(tmp_txt)
        assert len(logic.sections) == 2
        assert logic.source_type == 'text'

    def test_to_toon(self, tmp_txt):
        handler = TextHandler()
        logic = handler.parse(tmp_txt)
        toon = handler.to_spec(logic, 'toon')
        assert 'text' in toon
        assert 'P[' in toon


# =============================================================================
# Stage 2: Data & Config Handlers
# =============================================================================

class TestCsvHandler:
    def test_resolve(self, tmp_csv):
        handler = FormatRegistry.resolve(tmp_csv)
        assert isinstance(handler, CsvHandler)

    def test_parse(self, tmp_csv):
        handler = CsvHandler()
        logic = handler.parse(tmp_csv)
        assert logic.rows == 3
        assert len(logic.columns) == 4
        assert logic.columns[0].dtype == 'int'
        assert logic.columns[1].dtype == 'string'

    def test_to_toon(self, tmp_csv):
        handler = CsvHandler()
        logic = handler.parse(tmp_csv)
        toon = handler.to_spec(logic, 'toon')
        assert 'csv' in toon.lower()
        assert 'C[' in toon

    def test_reproduce(self, tmp_csv):
        handler = CsvHandler()
        logic = handler.parse(tmp_csv)
        reproduced = handler.reproduce(logic)
        assert 'id' in reproduced
        assert 'name' in reproduced


class TestJsonDataHandler:
    def test_resolve(self, tmp_json):
        handler = FormatRegistry.resolve(tmp_json)
        assert isinstance(handler, JsonDataHandler)

    def test_parse(self, tmp_json):
        handler = JsonDataHandler()
        logic = handler.parse(tmp_json)
        assert logic.root_type == 'object'
        assert logic.total_keys > 0

    def test_to_toon(self, tmp_json):
        handler = JsonDataHandler()
        logic = handler.parse(tmp_json)
        toon = handler.to_spec(logic, 'toon')
        assert 'json-data' in toon

    def test_negative_sniff_package_json(self):
        handler = JsonDataHandler()
        score = handler.sniff(Path("package.json"), '{"name": "pkg"}')
        assert score == 0.0


class TestEnvHandler:
    def test_resolve(self, tmp_env):
        handler = FormatRegistry.resolve(tmp_env)
        assert isinstance(handler, EnvHandler)

    def test_parse(self, tmp_env):
        handler = EnvHandler()
        logic = handler.parse(tmp_env)
        assert len(logic.entries) == 4
        secret = [e for e in logic.entries if e.key == 'API_SECRET_KEY'][0]
        assert secret.sensitive is True
        assert secret.description == '***'

    def test_to_toon_masks_sensitive(self, tmp_env):
        handler = EnvHandler()
        logic = handler.parse(tmp_env)
        toon = handler.to_spec(logic, 'toon')
        assert '***' in toon
        assert 'env' in toon.lower()

    def test_reproduce(self, tmp_env):
        handler = EnvHandler()
        logic = handler.parse(tmp_env)
        reproduced = handler.reproduce(logic)
        assert 'CHANGE_ME' in reproduced  # sensitive values masked


# =============================================================================
# Stage 3: Database, API, Infra Handlers
# =============================================================================

class TestSqlHandler:
    def test_resolve(self, tmp_sql):
        handler = FormatRegistry.resolve(tmp_sql)
        assert isinstance(handler, SqlHandler)

    def test_parse(self, tmp_sql):
        handler = SqlHandler()
        logic = handler.parse(tmp_sql)
        assert logic.dialect == 'postgresql'
        assert len(logic.tables) == 2
        assert len(logic.views) == 1

    def test_to_toon(self, tmp_sql):
        handler = SqlHandler()
        logic = handler.parse(tmp_sql)
        toon = handler.to_spec(logic, 'toon')
        assert 'postgresql' in toon
        assert 'T[2]' in toon
        assert 'V[1]' in toon

    def test_reproduce(self, tmp_sql):
        handler = SqlHandler()
        logic = handler.parse(tmp_sql)
        reproduced = handler.reproduce(logic)
        assert 'CREATE TABLE' in reproduced

    def test_detect_mysql(self, tmp_path):
        p = tmp_path / "mysql.sql"
        p.write_text("CREATE TABLE t (id INT AUTO_INCREMENT);")
        handler = SqlHandler()
        logic = handler.parse(p)
        assert logic.dialect == 'mysql'


class TestContentSniffing:
    """Test content sniffing disambiguation for .yaml files."""

    def test_k8s_beats_gh_on_deployment(self):
        k8s_content = "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: myapp"
        k8s_handler = KubernetesHandler()
        gh_handler = GithubActionsHandler()

        k8s_score = k8s_handler.sniff(Path("deployment.yaml"), k8s_content)
        gh_score = gh_handler.sniff(Path("deployment.yaml"), k8s_content)
        assert k8s_score > gh_score

    def test_gh_beats_k8s_on_workflow(self):
        gh_content = "name: CI\non:\n  push:\n    branches: [main]\njobs:\n  test:\n    runs-on: ubuntu-latest"
        k8s_handler = KubernetesHandler()
        gh_handler = GithubActionsHandler()

        gh_score = gh_handler.sniff(Path(".github/workflows/ci.yml"), gh_content)
        k8s_score = k8s_handler.sniff(Path(".github/workflows/ci.yml"), gh_content)
        assert gh_score > k8s_score

    def test_openapi_beats_k8s(self):
        openapi_content = "openapi: '3.0.0'\ninfo:\n  title: My API\npaths:\n  /users:"
        api_handler = OpenApiHandler()
        k8s_handler = KubernetesHandler()

        api_score = api_handler.sniff(Path("api.yaml"), openapi_content)
        k8s_score = k8s_handler.sniff(Path("api.yaml"), openapi_content)
        assert api_score > k8s_score
