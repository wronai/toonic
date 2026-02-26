"""
LLM Router — routes requests to appropriate models based on content type.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from toonic.server.config import ModelConfig, ServerConfig
from toonic.server.models import ActionResponse, SourceCategory

logger = logging.getLogger("toonic.router")


@dataclass
class LLMRequest:
    """Request to send to an LLM."""
    context: str
    goal: str
    category: str = "text"
    images: List[str] = None       # base64 images
    model_override: str = ""

    def __post_init__(self):
        if self.images is None:
            self.images = []


class LLMRouter:
    """Routes LLM requests to appropriate models based on content category."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self._clients: Dict[str, Any] = {}
        self._total_tokens = 0
        self._total_requests = 0

    def _get_model_for_category(self, category: str) -> ModelConfig:
        """Select model based on content category."""
        mapping = {
            "code": "code",
            "config": "code",
            "database": "code",
            "api": "code",
            "infra": "code",
            "logs": "text",
            "document": "text",
            "data": "text",
            "video": "multimodal",
            "audio": "multimodal",
        }
        model_key = mapping.get(category, "text")
        return self.config.models.get(model_key, self.config.models.get("text", ModelConfig()))

    async def query(self, request: LLMRequest) -> ActionResponse:
        """Send request to appropriate LLM and return response."""
        start = time.time()
        model_cfg = self._get_model_for_category(request.category)
        if request.model_override:
            model_cfg = ModelConfig(model=request.model_override)

        try:
            response_text = await self._call_llm(model_cfg, request)
            self._total_requests += 1
            duration = time.time() - start

            action = self._parse_response(response_text)
            action.model_used = model_cfg.model
            action.duration_s = duration
            action.action_id = f"action-{self._total_requests}"
            return action

        except Exception as e:
            logger.error(f"LLM error ({model_cfg.model}): {e}")
            return ActionResponse(
                action_type="error",
                content=f"LLM error: {e}",
                model_used=model_cfg.model,
                duration_s=time.time() - start,
            )

    async def _call_llm(self, model_cfg: ModelConfig, request: LLMRequest) -> str:
        """Call LLM via litellm or direct HTTP."""
        try:
            import litellm
            litellm.set_verbose = False

            messages = [
                {"role": "system", "content": self._system_prompt(request.goal)},
            ]

            # Build user message
            if request.images:
                content = [{"type": "text", "text": request.context}]
                for img_b64 in request.images[:5]:  # max 5 images
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    })
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": request.context})

            api_key = os.environ.get(model_cfg.api_key_env, os.environ.get("OPENROUTER_API_KEY", ""))
            response = await litellm.acompletion(
                model=model_cfg.model,
                messages=messages,
                max_tokens=model_cfg.max_tokens,
                api_key=api_key or None,
                base_url=model_cfg.base_url or None,
            )

            text = response.choices[0].message.content
            self._total_tokens += response.usage.total_tokens if response.usage else 0
            return text

        except ImportError:
            logger.warning("litellm not installed — using mock response")
            return self._mock_response(request)

    def _mock_response(self, request: LLMRequest) -> str:
        """Mock response when litellm is not available."""
        return json.dumps({
            "action": "report",
            "content": f"[MOCK] Analysis for goal: {request.goal}\n\n"
                       f"Context received: {len(request.context)} chars, "
                       f"category: {request.category}\n\n"
                       f"This is a mock response. Install litellm for real LLM integration:\n"
                       f"  pip install litellm",
            "confidence": 0.0,
        })

    def _system_prompt(self, goal: str) -> str:
        return (
            "You are Toonic, an AI assistant that analyzes projects and data streams.\n"
            "You receive context in TOON format (Token-Oriented Object Notation) — "
            "a compact representation of code, documents, configs, logs, and multimedia.\n\n"
            f"Current goal: {goal}\n\n"
            "Respond with a JSON object:\n"
            '{"action": "report|code_fix|alert|none", '
            '"content": "your analysis or fix", '
            '"target_path": "file to modify (if code_fix)", '
            '"confidence": 0.0-1.0, '
            '"affected_files": ["list", "of", "files"]}'
        )

    def _parse_response(self, text: str) -> ActionResponse:
        """Parse LLM response into ActionResponse."""
        try:
            # Try to extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return ActionResponse(
                    action_type=data.get("action", "report"),
                    content=data.get("content", text),
                    target_path=data.get("target_path", ""),
                    confidence=float(data.get("confidence", 0.5)),
                    affected_files=data.get("affected_files", []),
                )
        except (json.JSONDecodeError, ValueError):
            pass

        return ActionResponse(
            action_type="report",
            content=text,
            confidence=0.5,
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
            "models": {k: v.model for k, v in self.config.models.items()},
        }
