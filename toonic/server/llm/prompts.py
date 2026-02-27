"""
Prompt Builders — different strategies per use-case.

Each builder implements the PromptBuilder protocol:
    build(goal, chunks, images) -> {"system": str, "user": str, "images": list[str]}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from toonic.server.models import ContextChunk, SourceCategory


class PromptBuilder(Protocol):
    """Builds prompt from context. Different implementations per use-case."""

    def build(
        self,
        goal: str,
        chunks: List[ContextChunk],
        images: List[str],
    ) -> Dict[str, Any]:
        """Returns {'system': str, 'user': str, 'images': list[str]}."""
        ...


@dataclass
class GenericPrompt:
    """Default prompt — works for any data type."""

    def build(self, goal: str, chunks: List[ContextChunk], images: List[str]) -> Dict[str, Any]:
        system = (
            "You are Toonic — an intelligent data analysis assistant.\n"
            "You receive context in TOON format (Token-Oriented Object Notation) — "
            "a compact representation of code, documents, configs, logs, and multimedia.\n\n"
            "Respond with a JSON object:\n"
            '{"action": "report"|"code_fix"|"alert"|"none", '
            '"content": "your analysis", '
            '"target_path": "file to modify (if code_fix)", '
            '"confidence": 0.0-1.0, '
            '"affected_files": ["list", "of", "files"]}'
        )

        user_parts = [f"Goal: {goal}\n"]
        for chunk in chunks:
            cat = chunk.category.value if hasattr(chunk.category, "value") else str(chunk.category)
            user_parts.append(f"--- [{cat}] {chunk.source_id} ---")
            spec = chunk.toon_spec or ""
            if spec:
                user_parts.append(spec[:2000])
        if images:
            user_parts.append(f"\n[{len(images)} images attached]")

        return {"system": system, "user": "\n".join(user_parts), "images": images}


@dataclass
class CodeAnalysisPrompt:
    """Prompt optimized for code analysis — understands TOON spec."""

    def build(self, goal: str, chunks: List[ContextChunk], images: List[str]) -> Dict[str, Any]:
        code_chunks = [c for c in chunks if c.category in (
            SourceCategory.CODE, SourceCategory.CONFIG, SourceCategory.DATABASE
        )]
        log_chunks = [c for c in chunks if c.category == SourceCategory.LOGS]

        system = (
            "You are a code analysis assistant. You receive source code "
            "compressed in TOON format (Token-Oriented Object Notation).\n"
            "TOON uses compact notation: M=modules, c=classes, f=functions, "
            "m=methods, i=imports, e=exports.\n\n"
            "Respond with structured JSON:\n"
            '{"action": "code_fix"|"report"|"alert"|"none",\n'
            ' "content": "analysis",\n'
            ' "findings": [{"file": str, "line": int, "severity": '
            '"critical"|"high"|"medium"|"low",\n'
            '   "description": str, "fix": str}],\n'
            ' "confidence": float,\n'
            ' "affected_files": []}'
        )

        user_parts = [f"Goal: {goal}\n"]
        if code_chunks:
            user_parts.append("## Source code (TOON format)")
            for c in code_chunks:
                user_parts.append(c.toon_spec or "")
        if log_chunks:
            user_parts.append("\n## Recent logs")
            for c in log_chunks[-5:]:
                user_parts.append(c.toon_spec or "")

        return {"system": system, "user": "\n".join(user_parts), "images": []}


@dataclass
class CCTVEventPrompt:
    """Prompt for CCTV — enforces event analysis instead of scene description."""

    def build(self, goal: str, chunks: List[ContextChunk], images: List[str]) -> Dict[str, Any]:
        # Extract YOLO detection metadata from video chunks
        detection_info = []
        for chunk in chunks:
            if chunk.category == SourceCategory.VIDEO:
                meta = chunk.metadata or {}
                detections = meta.get("detected_objects", meta.get("detections", []))
                if detections:
                    if isinstance(detections, list):
                        labels = ", ".join(
                            f"{d.get('label', '?')}({d.get('confidence', 0):.0%})"
                            for d in detections
                            if isinstance(d, dict)
                        )
                    else:
                        labels = str(detections)
                    detection_info.append(f"  {chunk.source_id}: {labels}")

        system = (
            "You are a CCTV event analysis system.\n"
            "You receive multi-frame image sequences with YOLO pre-detections.\n\n"
            "CRITICAL RULES:\n"
            "- Do NOT describe the static scene.\n"
            "- Analyze the EVENT: actions, trajectory, behavior.\n"
            "- Compare frames: note movement direction, speed, appearing/disappearing objects.\n"
            "- For detected objects: describe their actions, trajectory, interactions.\n"
            "- Classify events: normal_activity, suspicious, intrusion, vehicle_entry, "
            "package_delivery, animal, weather_change, equipment_fault.\n\n"
            "Respond as JSON:\n"
            '{"action": "alert"|"report",\n'
            ' "content": "event description",\n'
            ' "event_type": str,\n'
            ' "objects": [{"type": str, "action": str, "direction": str}],\n'
            ' "severity": "normal"|"attention"|"alert"|"critical",\n'
            ' "confidence": float}'
        )

        user_parts = [f"Goal: {goal}\n"]
        if detection_info:
            user_parts.append("Pre-detections (YOLO):")
            user_parts.extend(detection_info)
        user_parts.append(f"\nAnalyze the {len(images)} attached frames.")

        return {"system": system, "user": "\n".join(user_parts), "images": images}


# Categories that should NEVER trigger CodeAnalysisPrompt.
_NON_CODE_CATEGORIES = {
    SourceCategory.WEB, SourceCategory.API, SourceCategory.NETWORK,
    SourceCategory.VIDEO, SourceCategory.AUDIO, SourceCategory.LOGS,
    SourceCategory.DATA, SourceCategory.DOCUMENT,
    SourceCategory.CONTAINER, SourceCategory.PROCESS, SourceCategory.INFRA,
}


def select_prompt_builder(goal: str, categories: set) -> PromptBuilder:
    """Auto-select PromptBuilder based on goal and data categories."""
    goal_lower = goal.lower()

    # CCTV keywords
    cctv_keywords = {"cctv", "camera", "security cam", "intrusion", "surveillance"}
    if SourceCategory.VIDEO in categories and any(k in goal_lower for k in cctv_keywords):
        return CCTVEventPrompt()

    # If ALL categories are non-code, never use CodeAnalysisPrompt regardless of goal.
    has_code = bool(categories & {SourceCategory.CODE, SourceCategory.CONFIG})
    all_non_code = categories and categories <= _NON_CODE_CATEGORIES

    if has_code and not all_non_code:
        return CodeAnalysisPrompt()

    # Goal-based fallback: only if no structured categories provided.
    code_keywords = {"code", "bug", "refactor", "quality", "analyze code"}
    if not categories and any(k in goal_lower for k in code_keywords):
        return CodeAnalysisPrompt()

    return GenericPrompt()
