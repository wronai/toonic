"""
Autopilot Loop — the main autonomous development cycle.

Cycle:
  1. Watch project files (via toonic-server watchers)
  2. Read ROADMAP.md to determine next task
  3. Send context + roadmap to LLM with AutopilotPrompt
  4. Parse response → file changes
  5. Execute changes via ActionExecutor
  6. Run tests
  7. If tests pass → update ROADMAP → commit (optional)
  8. If tests fail → send FixPrompt → retry
  9. Repeat
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from toonic.autopilot.executor import ActionExecutor, ExecutionResult
from toonic.autopilot.prompts import AutopilotPrompt, FixPrompt

logger = logging.getLogger("toonic.autopilot.loop")


@dataclass
class AutopilotConfig:
    """Configuration for the autopilot loop."""
    project_dir: str = "."
    goal: str = "build MVP"
    max_iterations: int = 20
    interval_s: float = 10.0
    max_fix_retries: int = 3
    dry_run: bool = False
    auto_test: bool = True
    auto_commit: bool = False
    model: str = ""
    api_key: str = ""
    provider: str = "openrouter"
    port: int = 8900


class AutopilotLoop:
    """Main autonomous development loop."""

    def __init__(self, config: AutopilotConfig):
        self.config = config
        self.project_dir = Path(config.project_dir).resolve()
        self.executor = ActionExecutor(
            project_dir=self.project_dir,
            dry_run=config.dry_run,
            auto_test=False,  # We manage test cycle ourselves
        )
        self.prompt = AutopilotPrompt()
        self.fix_prompt = FixPrompt()
        self._iteration = 0
        self._actions_log: List[Dict] = []
        self._running = False
        self._on_event: Optional[Callable] = None
        self._last_test_output: str = ""

    async def run(self, on_event: Optional[Callable] = None) -> List[Dict]:
        """Run the full autopilot loop. Returns action log."""
        self._on_event = on_event
        self._running = True

        await self._emit("start", {"project": str(self.project_dir), "goal": self.config.goal})
        logger.info(f"Autopilot starting: {self.project_dir} — goal: {self.config.goal}")

        # Initialize LLM caller
        from toonic.server.llm.caller import LLMCaller
        from toonic.server.llm.parser import ResponseParser

        caller = LLMCaller(
            api_key=self.config.api_key or os.environ.get("OPENROUTER_API_KEY", ""),
            provider=self.config.provider,
            default_model=self.config.model or "google/gemini-2.0-flash-001",
            max_tokens=16384,
        )
        parser = ResponseParser()

        # Main loop
        for i in range(self.config.max_iterations):
            if not self._running:
                break

            self._iteration = i + 1
            await self._emit("iteration_start", {"iteration": self._iteration})
            logger.info(f"\n{'='*60}\n  Iteration {self._iteration}/{self.config.max_iterations}\n{'='*60}")

            try:
                # Step 1: Scan project
                chunks = await self._scan_project()
                roadmap = self._read_roadmap()

                # Step 2: Build prompt
                previous_actions = self._format_previous_actions()
                prompt_data = self.prompt.build(
                    goal=self.config.goal,
                    chunks=chunks,
                    images=[],
                    roadmap=roadmap,
                    iteration=self._iteration,
                    test_output=self._last_test_output,
                    previous_actions=previous_actions,
                )

                # Step 3: Call LLM
                await self._emit("llm_call", {"iteration": self._iteration})
                raw_response = await caller.call(
                    model=caller.default_model,
                    system=prompt_data["system"],
                    user=prompt_data["user"],
                )

                content = raw_response.get("content", "")
                if not content:
                    logger.warning(f"Empty LLM response: {raw_response.get('error', 'unknown')}")
                    await self._emit("error", {"message": "Empty LLM response"})
                    await asyncio.sleep(self.config.interval_s)
                    continue

                # Step 4: Parse response
                action_data = parser.parse_raw_to_dict(content)
                if not action_data:
                    # Try direct JSON parse
                    try:
                        action_data = json.loads(content)
                    except json.JSONDecodeError:
                        action_data = {"action": "report", "content": content}

                await self._emit("llm_response", {
                    "iteration": self._iteration,
                    "action": action_data.get("action", "unknown"),
                    "description": action_data.get("description", "")[:200],
                    "files_count": len(action_data.get("files", [])),
                })

                # Step 5: Execute file changes
                result = self.executor.execute(action_data)
                log_entry = {
                    "iteration": self._iteration,
                    "action": action_data.get("action", "unknown"),
                    "description": action_data.get("description", ""),
                    "files_written": result.files_written,
                    "success": result.success,
                    "error": result.error,
                }

                # Step 6: Run tests
                if result.files_written and self.config.auto_test:
                    test_result = self.executor._execute_tests()
                    log_entry["tests_passed"] = test_result.success
                    log_entry["test_output"] = test_result.test_output[:500]

                    if test_result.success:
                        self._last_test_output = ""
                    else:
                        self._last_test_output = test_result.test_output

                    # Step 7: Fix loop if tests fail
                    if not test_result.success:
                        fix_result = await self._fix_loop(
                            caller, parser, chunks, test_result.test_output
                        )
                        log_entry["fix_applied"] = fix_result
                        if fix_result:
                            self._last_test_output = ""

                    # Step 8: Update roadmap
                    roadmap_update = action_data.get("roadmap_update", "")
                    if roadmap_update and (not self.config.auto_test or test_result.success):
                        self._update_roadmap(roadmap_update)

                self._actions_log.append(log_entry)
                await self._emit("iteration_done", log_entry)

                logger.info(f"  Result: {len(result.files_written)} files written, "
                          f"success={result.success}")

                # Check if roadmap is complete
                if self._is_roadmap_complete():
                    logger.info("ROADMAP complete! All tasks done.")
                    await self._emit("complete", {"iterations": self._iteration})
                    break

            except Exception as e:
                logger.error(f"Iteration {self._iteration} error: {e}", exc_info=True)
                await self._emit("error", {"iteration": self._iteration, "error": str(e)})

            await asyncio.sleep(self.config.interval_s)

        self._running = False
        await self._emit("stop", {"iterations": self._iteration, "total_actions": len(self._actions_log)})
        return self._actions_log

    def stop(self):
        """Stop the autopilot loop."""
        self._running = False

    async def _fix_loop(self, caller, parser, chunks, test_output: str) -> bool:
        """Try to fix failing tests."""
        for attempt in range(self.config.max_fix_retries):
            logger.info(f"  Fix attempt {attempt + 1}/{self.config.max_fix_retries}")

            # Re-scan project to see latest code (files changed by previous attempt)
            fresh_chunks = await self._scan_project()

            prompt_data = self.fix_prompt.build(
                goal=self.config.goal,
                test_output=test_output,
                chunks=fresh_chunks,
            )

            raw = await caller.call(
                model=caller.default_model,
                system=prompt_data["system"],
                user=prompt_data["user"],
            )

            content = raw.get("content", "")
            if not content:
                continue

            action_data = parser.parse_raw_to_dict(content)
            if not action_data:
                try:
                    action_data = json.loads(content)
                except json.JSONDecodeError:
                    continue

            result = self.executor.execute(action_data)
            if result.files_written:
                test_result = self.executor._execute_tests()
                if test_result.success:
                    logger.info(f"  Fix successful on attempt {attempt + 1}")
                    return True
                test_output = test_result.test_output

        logger.warning("  Could not fix tests after max retries")
        return False

    async def _scan_project(self) -> list:
        """Scan project files and create ContextChunks."""
        from toonic.server.models import ContextChunk, SourceCategory, ContentType

        chunks = []
        project = self.project_dir

        for path in sorted(project.rglob("*")):
            if not path.is_file():
                continue
            # Skip hidden, __pycache__, node_modules, toonic_data
            rel = str(path.relative_to(project))
            if any(part.startswith(".") or part in ("__pycache__", "node_modules", "toonic_data", ".git")
                   for part in path.parts):
                continue
            if path.suffix in (".pyc", ".pyo", ".so", ".o"):
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue
            except (UnicodeDecodeError, PermissionError):
                continue

            # Determine category
            if path.suffix in (".py", ".js", ".ts", ".rs", ".go", ".java"):
                cat = SourceCategory.CODE
            elif path.suffix in (".yaml", ".yml", ".toml", ".json", ".ini", ".cfg"):
                cat = SourceCategory.CONFIG
            elif path.suffix in (".md", ".rst", ".txt"):
                cat = SourceCategory.DOCUMENT
            elif path.suffix in (".log",):
                cat = SourceCategory.LOGS
            else:
                cat = SourceCategory.DATA

            # Create TOON-like spec
            toon_spec = f"# {rel}\n{content[:4000]}"

            chunks.append(ContextChunk(
                source_id=rel,
                category=cat,
                toon_spec=toon_spec,
                content_type=ContentType.TOON_SPEC,
                priority=0.8 if cat == SourceCategory.CODE else 0.5,
            ))

        logger.info(f"  Scanned {len(chunks)} files")
        return chunks

    def _read_roadmap(self) -> str:
        """Read ROADMAP.md content."""
        roadmap_path = self.project_dir / "ROADMAP.md"
        if roadmap_path.exists():
            return roadmap_path.read_text(encoding="utf-8")
        return ""

    def _update_roadmap(self, update: str):
        """Update ROADMAP.md with completed tasks."""
        roadmap_path = self.project_dir / "ROADMAP.md"
        if not roadmap_path.exists():
            return

        current = roadmap_path.read_text(encoding="utf-8")
        # Simple: replace unchecked items with checked ones from update
        for line in update.split("\n"):
            line = line.strip()
            if line.startswith("- [x]"):
                task = line[5:].strip()
                unchecked = f"- [ ] {task}"
                if unchecked in current:
                    current = current.replace(unchecked, f"- [x] {task}")

        roadmap_path.write_text(current, encoding="utf-8")
        logger.info("  ROADMAP.md updated")

    def _is_roadmap_complete(self) -> bool:
        """Check if all roadmap tasks are done."""
        roadmap = self._read_roadmap()
        if not roadmap:
            return False
        unchecked = roadmap.count("- [ ]")
        checked = roadmap.count("- [x]")
        return unchecked == 0 and checked > 0

    def _format_previous_actions(self) -> str:
        """Format recent actions for context."""
        if not self._actions_log:
            return ""
        recent = self._actions_log[-3:]
        lines = []
        for a in recent:
            lines.append(f"- Iteration {a['iteration']}: {a.get('description', '')[:100]}")
            if a.get("files_written"):
                lines.append(f"  Files: {', '.join(a['files_written'])}")
            if a.get("error"):
                lines.append(f"  Error: {a['error'][:100]}")
        return "\n".join(lines)

    async def _emit(self, event_type: str, data: Dict[str, Any]):
        """Emit event to callback."""
        if self._on_event:
            try:
                await self._on_event(event_type, data)
            except Exception:
                pass
