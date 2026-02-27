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
