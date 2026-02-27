"""
LLM Caller — handles API calls with retry and exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("toonic.llm.caller")


@dataclass
class LLMCaller:
    """Calls LLM API with retry, timeout, and metrics."""

    api_key: str = ""
    provider: str = "openrouter"
    default_model: str = "google/gemini-3-flash-preview"
    max_retries: int = 2
    timeout_s: float = 60.0
    max_tokens: int = 8192
    base_url: str = ""

    # Model routing per category
    model_map: Dict[str, str] = field(default_factory=lambda: {
        "code": "google/gemini-3-flash-preview",
        "text": "google/gemini-3-flash-preview",
        "multimodal": "google/gemini-3-flash-preview",
    })

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get(
                "LLM_API_KEY",
                os.environ.get("OPENROUTER_API_KEY", ""),
            )
        if not self.base_url:
            self.base_url = os.environ.get("LLM_BASE_URL", "")

    def select_model(self, category: str, has_images: bool = False) -> str:
        """Select model based on category and image presence."""
        if has_images:
            return self.model_map.get("multimodal", self.default_model)

        category_to_type = {
            "code": "code", "config": "code", "database": "code",
            "api": "code", "infra": "code",
            "logs": "text", "document": "text", "data": "text",
            "video": "multimodal", "audio": "multimodal",
        }
        model_type = category_to_type.get(category, "text")
        return self.model_map.get(model_type, self.default_model)

    def _litellm_model_id(self, model: str) -> str:
        """Add provider prefix if missing."""
        model = (model or "").strip()
        provider = (self.provider or "").strip()
        if not model:
            return model
        if provider and model.startswith(provider + "/"):
            return model
        if provider:
            return f"{provider}/{model}"
        return model

    async def call(
        self,
        model: str,
        system: str,
        user: str,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Call LLM with retry and exponential backoff."""
        try:
            import litellm
            litellm.set_verbose = False
        except ImportError:
            return self._mock_response(model, system, user)

        messages = [{"role": "system", "content": system}]

        # Build user message — with images if multimodal
        if images:
            content_parts = [{"type": "text", "text": user}]
            for img_b64 in images[:8]:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": user})

        model_id = self._litellm_model_id(model)
        last_error = None

        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            try:
                response = await litellm.acompletion(
                    model=model_id,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    api_key=self.api_key or None,
                    base_url=self.base_url or None,
                    timeout=self.timeout_s,
                )
                duration = time.time() - t0
                content = response.choices[0].message.content or ""
                tokens = int(getattr(getattr(response, "usage", None), "total_tokens", 0) or 0)

                logger.info(f"LLM call: model={model_id}, tokens={tokens}, duration={duration:.1f}s")

                return {
                    "content": content,
                    "model": model_id,
                    "tokens_used": tokens,
                    "duration_s": duration,
                    "finish_reason": response.choices[0].finish_reason,
                }
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)

        return {"content": "", "error": last_error, "model": model_id, "tokens_used": 0}

    def _mock_response(self, model: str, system: str, user: str) -> Dict[str, Any]:
        """Mock response when litellm is not installed."""
        model_id = self._litellm_model_id(model)
        mock_content = json.dumps({
            "action": "report",
            "content": f"[MOCK] Analysis received. Context: {len(user)} chars. "
                       f"Install litellm for real LLM integration: pip install litellm",
            "confidence": 0.0,
        })
        return {
            "content": mock_content,
            "model": model_id,
            "tokens_used": len(user.split()) * 4 // 3,
            "duration_s": 0.0,
            "finish_reason": "mock",
        }
