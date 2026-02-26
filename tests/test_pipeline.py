"""
Tests for toonic.pipeline — Stage 4: Pipeline & CLI
"""

import pytest
from pathlib import Path

from toonic.pipeline import Pipeline, ReproductionResult


class TestPipelineToSpec:
    """Test Pipeline.to_spec() — file → spec."""

    def test_markdown_to_toon(self, tmp_md):
        spec = Pipeline.to_spec(str(tmp_md), fmt='toon')
        assert 'D[' in spec or 'markdown' in spec.lower()

    def test_csv_to_toon(self, tmp_csv):
        spec = Pipeline.to_spec(str(tmp_csv), fmt='toon')
        assert 'csv' in spec.lower() or 'C[' in spec

    def test_env_to_toon(self, tmp_env):
        spec = Pipeline.to_spec(str(tmp_env), fmt='toon')
        assert 'env' in spec.lower()
        assert '***' in spec

    def test_sql_to_toon(self, tmp_sql):
        spec = Pipeline.to_spec(str(tmp_sql), fmt='toon')
        assert 'postgresql' in spec
        assert 'T[' in spec

    def test_json_to_toon(self, tmp_json):
        spec = Pipeline.to_spec(str(tmp_json), fmt='toon')
        assert 'json-data' in spec

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            Pipeline.to_spec('/nonexistent/file.md')

    def test_output_to_file(self, tmp_md, tmp_path):
        out_file = str(tmp_path / "output.toon")
        Pipeline.to_spec(str(tmp_md), fmt='toon', output=out_file)
        assert Path(out_file).exists()
        content = Path(out_file).read_text()
        assert len(content) > 0


class TestPipelineRoundtrip:
    """Test Pipeline.roundtrip() — file → spec → reproduced."""

    def test_markdown_roundtrip(self, tmp_md):
        result = Pipeline.roundtrip(str(tmp_md), fmt='toon')
        assert isinstance(result, ReproductionResult)
        assert result.duration_seconds > 0


class TestPipelineBatch:
    """Test Pipeline.batch() — process directory."""

    def test_batch_processing(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Test\n\nHello world.\n")
        (tmp_path / "data.csv").write_text("x,y\n1,2\n3,4\n")

        out_dir = tmp_path / "specs"
        results = Pipeline.batch(str(tmp_path), fmt='toon', output_dir=str(out_dir))
        assert len(results) >= 2

        for r in results:
            assert Path(r).exists()

    def test_batch_not_a_directory(self, tmp_md):
        with pytest.raises(NotADirectoryError):
            Pipeline.batch(str(tmp_md))


class TestPipelineFormats:
    """Test Pipeline.formats() — list available handlers."""

    def test_formats_structure(self):
        info = Pipeline.formats()
        assert 'categories' in info
        assert 'available' in info
        assert 'total_handlers' in info
        assert info['total_handlers'] > 5

    def test_has_expected_categories(self):
        info = Pipeline.formats()
        cats = info['categories']
        assert 'document' in cats
        assert 'data' in cats
        assert 'database' in cats
