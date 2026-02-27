"""
Autopilot Prompt Builders — instruct LLM to generate concrete file changes.

Unlike analysis prompts (report-only), these produce actionable code output
that the ActionExecutor can apply to the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from toonic.server.models import ContextChunk, SourceCategory


@dataclass
class AutopilotPrompt:
    """Prompt that instructs LLM to generate concrete file changes for the project."""

    def build(self, goal: str, chunks: List[ContextChunk], images: List[str],
              roadmap: str = "", iteration: int = 0,
              test_output: str = "", previous_actions: str = "") -> Dict[str, Any]:

        system = (
            "You are Toonic Autopilot — an autonomous software development agent.\n"
            "Your job is to BUILD and IMPROVE a project incrementally.\n\n"
            "RULES:\n"
            "1. Generate CONCRETE file changes — not reports or suggestions.\n"
            "2. Each response MUST contain code in named file blocks.\n"
            "3. Follow the project's ROADMAP — pick the next unchecked task.\n"
            "4. Write tests alongside implementation code.\n"
            "5. Keep changes small and focused (1-3 files per iteration).\n"
            "6. If tests failed, fix the failing code first.\n\n"
            "RESPONSE FORMAT (JSON):\n"
            '{\n'
            '  "action": "implement",\n'
            '  "description": "what you did and why",\n'
            '  "files": [\n'
            '    {"path": "relative/path/file.py", "content": "full file content"},\n'
            '    {"path": "tests/test_file.py", "content": "test code"}\n'
            '  ],\n'
            '  "roadmap_update": "- [x] task completed\\n- [ ] next task",\n'
            '  "next_step": "what should be done next",\n'
            '  "confidence": 0.8\n'
            '}\n\n'
            "IMPORTANT:\n"
            "- Each file in 'files' must contain the COMPLETE file content.\n"
            "- Use proper imports, type hints, docstrings.\n"
            "- Tests must be runnable with pytest (Python) or jest (JS).\n"
            "- If you see test failures, fix them before adding new features."
        )

        user_parts = [f"## Goal\n{goal}\n"]

        # Add iteration context
        if iteration > 0:
            user_parts.append(f"## Iteration #{iteration}\n")

        # Add roadmap
        if roadmap:
            user_parts.append(f"## ROADMAP (check next unchecked task)\n{roadmap}\n")

        # Add test output if tests failed
        if test_output:
            user_parts.append(f"## Test Output (fix these first!)\n```\n{test_output[-1500:]}\n```\n")

        # Add previous actions summary
        if previous_actions:
            user_parts.append(f"## Previous Actions\n{previous_actions}\n")

        # Add current project code
        code_chunks = [c for c in chunks if c.category in (
            SourceCategory.CODE, SourceCategory.CONFIG
        )]
        if code_chunks:
            user_parts.append("## Current Project Code (TOON format)")
            for c in code_chunks:
                user_parts.append(f"--- [{c.source_id}] ---")
                spec = c.toon_spec or ""
                if spec:
                    user_parts.append(spec[:3000])

        # Other chunks (logs, data)
        other_chunks = [c for c in chunks if c.category not in (
            SourceCategory.CODE, SourceCategory.CONFIG
        )]
        if other_chunks:
            user_parts.append("\n## Other Context")
            for c in other_chunks[-5:]:
                user_parts.append(f"[{c.category.value}] {c.toon_spec[:500]}")

        return {"system": system, "user": "\n".join(user_parts), "images": images}


@dataclass
class ScaffoldPrompt:
    """Prompt for initial project scaffolding from a description.

    Used when the project is empty and needs initial structure.
    """

    def build(self, description: str, name: str, language: str = "python",
              project_type: str = "cli") -> Dict[str, Any]:

        system = (
            "You are a project architect. Generate a complete project scaffold.\n\n"
            "RESPONSE FORMAT (JSON):\n"
            '{\n'
            '  "files": [\n'
            '    {"path": "relative/path", "content": "full content"}\n'
            '  ],\n'
            '  "roadmap": "markdown roadmap with phases and tasks",\n'
            '  "description": "refined project description"\n'
            '}\n\n'
            "Include: models, core logic, CLI/API entry point, tests, README, config."
        )

        user = (
            f"Project: {name}\n"
            f"Description: {description}\n"
            f"Language: {language}\n"
            f"Type: {project_type}\n\n"
            "Generate a complete project scaffold with working code and tests."
        )

        return {"system": system, "user": user, "images": []}


@dataclass
class FixPrompt:
    """Prompt specifically for fixing test failures."""

    def build(self, goal: str, test_output: str,
              chunks: List[ContextChunk]) -> Dict[str, Any]:

        system = (
            "You are a debugging agent. Fix the failing tests.\n\n"
            "RESPONSE FORMAT (JSON):\n"
            '{\n'
            '  "action": "code_fix",\n'
            '  "description": "what was wrong and how you fixed it",\n'
            '  "files": [\n'
            '    {"path": "file.py", "content": "full corrected content"}\n'
            '  ],\n'
            '  "confidence": 0.9\n'
            '}\n\n'
            "RULES:\n"
            "- Fix the ROOT CAUSE, not symptoms.\n"
            "- Include the COMPLETE file content, not just the changed lines.\n"
            "- Do not break other tests."
        )

        user_parts = [
            f"## Goal\n{goal}\n",
            f"## Test Failures\n```\n{test_output[-2000:]}\n```\n",
        ]

        for c in chunks:
            if c.category in (SourceCategory.CODE, SourceCategory.CONFIG):
                user_parts.append(f"--- [{c.source_id}] ---")
                user_parts.append(c.toon_spec[:3000])

        return {"system": system, "user": "\n".join(user_parts), "images": []}
