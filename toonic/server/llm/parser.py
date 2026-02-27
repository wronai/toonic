"""
Response Parser — parses raw LLM response into ActionResponse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict

from toonic.server.models import ActionResponse

logger = logging.getLogger("toonic.llm.parser")


@dataclass
class ResponseParser:
    """Parses raw LLM response dict into ActionResponse."""

    def parse(self, raw: Dict[str, Any], category: str = "code") -> ActionResponse:
        # Error from caller
        if raw.get("error"):
            return ActionResponse(
                action_type="error",
                content=raw["error"],
                confidence=0.0,
                model_used=raw.get("model", ""),
                tokens_used=raw.get("tokens_used", 0),
                duration_s=raw.get("duration_s", 0.0),
            )

        content = raw.get("content", "")

        # Try parsing JSON from response
        try:
            # LLM sometimes wraps JSON in ```json ... ```
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean
                clean = clean.rsplit("```", 1)[0]

            # Try to find JSON object in response
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(clean[start:end])
                return ActionResponse(
                    action_type=parsed.get("action", parsed.get("action_type", "report")),
                    content=parsed.get("content", content),
                    target_path=parsed.get("target_path", ""),
                    confidence=float(parsed.get("confidence", 0.5)),
                    affected_files=parsed.get("affected_files", []),
                    model_used=raw.get("model", ""),
                    tokens_used=raw.get("tokens_used", 0),
                    duration_s=raw.get("duration_s", 0.0),
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        # Fallback: plain text
        return ActionResponse(
            action_type="report",
            content=content,
            confidence=0.3,
            model_used=raw.get("model", ""),
            tokens_used=raw.get("tokens_used", 0),
            duration_s=raw.get("duration_s", 0.0),
        )

    def parse_raw_to_dict(self, content: str) -> Dict[str, Any] | None:
        """Parse raw LLM content string into a dict (for autopilot executor).

        Handles: ```json...```, thinking preamble, nested braces.
        """
        if not content or not content.strip():
            return None

        clean = content.strip()

        # Strip markdown fences (```json ... ```)
        import re
        fence_match = re.search(r'```(?:json)?\s*\n(.*?)```', clean, re.DOTALL)
        if fence_match:
            clean = fence_match.group(1).strip()

        # Find the outermost JSON object by brace matching
        start = clean.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape = False
        end = -1
        for i in range(start, len(clean)):
            c = clean[i]
            if escape:
                escape = False
                continue
            if c == '\\' and in_string:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end > start:
            try:
                return json.loads(clean[start:end])
            except json.JSONDecodeError:
                # Try with relaxed parsing — sometimes LLM outputs trailing commas
                try:
                    # Remove trailing commas before } or ]
                    relaxed = re.sub(r',\s*([}\]])', r'\1', clean[start:end])
                    return json.loads(relaxed)
                except json.JSONDecodeError:
                    pass
        return None
