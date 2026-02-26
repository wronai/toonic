"""
Tests for toonic.cli — CLI interface
"""

import pytest
from io import StringIO
import sys

from toonic.cli import cli_main


class TestCLI:
    def test_formats_command(self, capsys):
        cli_main(['formats'])
        captured = capsys.readouterr()
        assert 'document' in captured.out
        assert 'handlerów' in captured.out.lower() or 'handler' in captured.out.lower()

    def test_spec_command(self, tmp_md, capsys):
        cli_main(['spec', str(tmp_md)])
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_spec_csv_command(self, tmp_csv, capsys):
        cli_main(['spec', str(tmp_csv), '--fmt', 'toon'])
        captured = capsys.readouterr()
        assert 'csv' in captured.out.lower() or 'C[' in captured.out

    def test_spec_output_to_file(self, tmp_md, tmp_path):
        out = str(tmp_path / "out.toon")
        cli_main(['spec', str(tmp_md), '-o', out])
        from pathlib import Path
        assert Path(out).exists()

    def test_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            cli_main(['--help'])
        assert exc_info.value.code == 0

    def test_no_command(self, capsys):
        cli_main([])
        captured = capsys.readouterr()
        # Should print help or show usage
        assert len(captured.out) > 0 or len(captured.err) == 0
