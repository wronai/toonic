"""
Action Executor — applies LLM-generated actions to the project filesystem.

Handles:
  - code_fix: write/modify files based on LLM output
  - create_file: create new files with content
  - delete_file: remove files
  - run_tests: execute test suite
  - report: log analysis (no filesystem change)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("toonic.autopilot.executor")


@dataclass
class ExecutionResult:
    """Result of executing an action."""
    action_type: str
    success: bool = False
    files_written: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    test_output: str = ""
    error: str = ""
    duration_s: float = 0.0


class ActionExecutor:
    """Executes LLM-generated actions on the project filesystem."""

    def __init__(self, project_dir: str | Path, dry_run: bool = False,
                 auto_test: bool = True, auto_commit: bool = False):
        self.project_dir = Path(project_dir).resolve()
        self.dry_run = dry_run
        self.auto_test = auto_test
        self.auto_commit = auto_commit
        self._history: List[ExecutionResult] = []

    def execute(self, action: Dict[str, Any]) -> ExecutionResult:
        """Execute a single action from LLM response."""
        start = time.time()
        action_type = action.get("action_type", action.get("action", "none"))
        content = action.get("content", "")

        try:
            if action_type in ("code_fix", "create_file", "implement"):
                result = self._execute_code_change(action)
            elif action_type == "delete_file":
                result = self._execute_delete(action)
            elif action_type == "run_tests":
                result = self._execute_tests()
            elif action_type == "report":
                result = ExecutionResult(action_type="report", success=True)
                logger.info(f"Report: {content[:200]}")
            elif action_type == "none":
                result = ExecutionResult(action_type="none", success=True)
            else:
                result = self._execute_code_change(action)

            result.duration_s = time.time() - start

            # Auto-test after code changes
            if self.auto_test and result.files_written and result.success:
                test_result = self._execute_tests()
                result.test_output = test_result.test_output
                if not test_result.success:
                    logger.warning(f"Tests failed after code change: {test_result.test_output[:200]}")

            self._history.append(result)
            return result

        except Exception as e:
            result = ExecutionResult(
                action_type=action_type,
                error=str(e),
                duration_s=time.time() - start,
            )
            self._history.append(result)
            return result

    def _execute_code_change(self, action: Dict[str, Any]) -> ExecutionResult:
        """Extract file changes from LLM response and apply them."""
        content = action.get("content", "")
        target_path = action.get("target_path", "")
        affected_files = action.get("affected_files", [])

        files_written = []

        # Strategy 1: Explicit target_path + content with code blocks
        if target_path and content:
            code = self._extract_code(content)
            if code:
                written = self._write_file(target_path, code)
                if written:
                    files_written.append(written)

        # Strategy 2: Parse multiple file blocks from content
        # Format: ```filename.py\n..code..\n```
        file_blocks = self._extract_file_blocks(content)
        for fpath, fcode in file_blocks.items():
            written = self._write_file(fpath, fcode)
            if written:
                files_written.append(written)

        # Strategy 3: JSON with "files" array
        if not files_written:
            try:
                data = json.loads(content) if isinstance(content, str) else content
                if isinstance(data, dict) and "files" in data:
                    for fentry in data["files"]:
                        fp = fentry.get("path", fentry.get("file", ""))
                        fc = fentry.get("content", fentry.get("code", ""))
                        if fp and fc:
                            written = self._write_file(fp, fc)
                            if written:
                                files_written.append(written)
            except (json.JSONDecodeError, TypeError):
                pass

        return ExecutionResult(
            action_type="code_fix",
            success=bool(files_written),
            files_written=files_written,
            error="" if files_written else "No code blocks extracted from LLM response",
        )

    def _execute_delete(self, action: Dict[str, Any]) -> ExecutionResult:
        """Delete files specified in action."""
        target = action.get("target_path", "")
        affected = action.get("affected_files", [])
        paths = [target] + affected if target else affected

        deleted = []
        for p in paths:
            full = self._resolve_path(p)
            if full and full.exists() and full.is_file():
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Would delete: {full}")
                else:
                    full.unlink()
                    logger.info(f"Deleted: {full}")
                deleted.append(str(full.relative_to(self.project_dir)))

        return ExecutionResult(
            action_type="delete_file",
            success=bool(deleted),
            files_deleted=deleted,
        )

    def _execute_tests(self) -> ExecutionResult:
        """Run project tests."""
        # Detect test runner
        if (self.project_dir / "pyproject.toml").exists() or (self.project_dir / "tests").exists():
            cmd = ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-q"]
        elif (self.project_dir / "package.json").exists():
            cmd = ["npm", "test"]
        else:
            return ExecutionResult(action_type="run_tests", success=True,
                                   test_output="No test runner detected")

        if self.dry_run:
            return ExecutionResult(action_type="run_tests", success=True,
                                   test_output="[DRY-RUN] Would run tests")

        try:
            result = subprocess.run(
                cmd, cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            return ExecutionResult(
                action_type="run_tests",
                success=result.returncode == 0,
                test_output=output[-2000:],
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(action_type="run_tests", error="Test timeout (120s)")
        except Exception as e:
            return ExecutionResult(action_type="run_tests", error=str(e))

    # ── Helpers ──────────────────────────────────────────────────────

    def _resolve_path(self, rel_path: str) -> Optional[Path]:
        """Resolve relative path within project, preventing traversal."""
        if not rel_path:
            return None
        clean = rel_path.lstrip("./")
        full = (self.project_dir / clean).resolve()
        # Safety: must be inside project_dir
        if not str(full).startswith(str(self.project_dir)):
            logger.warning(f"Path traversal blocked: {rel_path}")
            return None
        return full

    def _write_file(self, rel_path: str, content: str) -> str:
        """Write content to file. Returns relative path or empty string."""
        full = self._resolve_path(rel_path)
        if not full:
            return ""

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would write: {full} ({len(content)} chars)")
            return str(full.relative_to(self.project_dir))

        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        logger.info(f"Wrote: {full} ({len(content)} chars)")
        return str(full.relative_to(self.project_dir))

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract code from markdown code blocks or raw text."""
        # Try to find a code block
        pattern = r'```(?:\w+)?\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()
        # If no code block, return stripped text if it looks like code
        lines = text.strip().split("\n")
        if any(line.strip().startswith(("import ", "from ", "def ", "class ", "const ", "function ")) for line in lines[:5]):
            return text.strip()
        return ""

    @staticmethod
    def _extract_file_blocks(text: str) -> Dict[str, str]:
        """Extract named file blocks: ```path/to/file.py\n...code...\n```"""
        files = {}
        # Pattern: ```<optional lang> path/file.ext\n...code...\n```
        # or: ### file: path/file.ext\n```\n...code...\n```
        pattern = r'(?:###?\s*(?:file:?\s*)?)?```(?:\w+\s+)?([a-zA-Z0-9_/.\-]+\.\w{1,5})\n(.*?)```'
        for match in re.finditer(pattern, text, re.DOTALL):
            fpath = match.group(1).strip()
            fcode = match.group(2).strip()
            if fpath and fcode and "/" in fpath or "." in fpath:
                files[fpath] = fcode

        return files

    def get_history(self) -> List[Dict[str, Any]]:
        """Get execution history."""
        return [
            {
                "action_type": r.action_type,
                "success": r.success,
                "files_written": r.files_written,
                "files_deleted": r.files_deleted,
                "error": r.error,
                "duration_s": r.duration_s,
            }
            for r in self._history
        ]
