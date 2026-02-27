"""
LLM Router — routes requests to appropriate models based on content type.

REFACTORED: delegates to LLMPipeline for prompt building, API calls, and parsing.
Keeps backward-compatible LLMRequest/query() interface.
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
from toonic.server.models import ActionResponse, ContextChunk, SourceCategory
from toonic.server.core.history import ConversationHistory, ExchangeRecord
from toonic.server.llm.caller import LLMCaller
from toonic.server.llm.parser import ResponseParser
from toonic.server.llm.pipeline import LLMPipeline

logger = logging.getLogger("toonic.router")


@dataclass
class LLMRequest:
    """Request to send to an LLM."""
    context: str
    goal: str
    category: str = "text"
    images: List[str] = None       # base64 images
    model_override: str = ""
    source_chunks: List[ContextChunk] = None

    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.source_chunks is None:
            self.source_chunks = []


class LLMRouter:
    """Routes LLM requests to appropriate models based on content category.

    REFACTORED: delegates to LLMPipeline for prompt + call + parse.
    """

    def __init__(self, config: ServerConfig, history: Optional['ConversationHistory'] = None):
        self.config = config
        self.history = history
        self._clients: Dict[str, Any] = {}
        self._total_tokens = 0
        self._total_requests = 0

        # Build pipeline from config
        self.pipeline = LLMPipeline(
            caller=LLMCaller(
                api_key=os.environ.get("LLM_API_KEY",
                         os.environ.get("OPENROUTER_API_KEY", "")),
                provider=os.environ.get("LLM_PROVIDER", "openrouter"),
                model_map={
                    "code": config.models.get("code", ModelConfig()).model,
                    "text": config.models.get("text", ModelConfig()).model,
                    "multimodal": config.models.get("multimodal", ModelConfig()).model,
                },
                max_tokens=config.models.get("text", ModelConfig()).max_tokens,
                base_url=config.models.get("text", ModelConfig()).base_url,
            ),
        )

    async def query(self, request: LLMRequest) -> ActionResponse:
        """Send request to appropriate LLM and return response.

        Backward-compatible interface — delegates to LLMPipeline.
        """
        start = time.time()
        self._total_requests += 1

        # Build chunks from legacy context string if no source_chunks
        chunks = request.source_chunks or []
        if not chunks and request.context:
            chunks = [ContextChunk(
                source_id="legacy",
                category=SourceCategory.CODE,
                toon_spec=request.context,
            )]

        # Override model in caller if requested
        if request.model_override:
            old_default = self.pipeline.caller.default_model
            old_map = dict(self.pipeline.caller.model_map)
            for key in self.pipeline.caller.model_map:
                self.pipeline.caller.model_map[key] = request.model_override
            self.pipeline.caller.default_model = request.model_override

        try:
            action = await self.pipeline.execute(
                goal=request.goal,
                category=request.category,
                chunks=chunks,
                images=request.images,
            )
            action.action_id = f"action-{self._total_requests}"
            self._total_tokens += action.tokens_used

            # Record to history
            model_cfg = self._get_model_for_category(request.category)
            self._record_exchange(request, action, model_cfg, time.time() - start, "ok")
            return action

        except Exception as e:
            logger.error(f"LLM error: {e}")
            action = ActionResponse(
                action_type="error",
                content=f"LLM error: {e}",
                model_used="",
                tokens_used=0,
                duration_s=time.time() - start,
            )
            model_cfg = self._get_model_for_category(request.category)
            self._record_exchange(request, action, model_cfg, time.time() - start, "error", str(e))
            return action

        finally:
            # Restore model if overridden
            if request.model_override:
                self.pipeline.caller.default_model = old_default
                self.pipeline.caller.model_map = old_map

    def _get_model_for_category(self, category: str) -> ModelConfig:
        """Select model based on content category."""
        mapping = {
            "code": "code", "config": "code", "database": "code",
            "api": "code", "infra": "code",
            "logs": "text", "document": "text", "data": "text",
            "video": "multimodal", "audio": "multimodal",
        }
        model_key = mapping.get(category, "text")
        return self.config.models.get(model_key, self.config.models.get("text", ModelConfig()))

    def _record_exchange(self, request: LLMRequest, action: ActionResponse,
                          model_cfg: ModelConfig, duration: float,
                          status: str = "ok", error: str = "") -> None:
        """Log exchange to ConversationHistory."""
        if not self.history:
            return
        try:
            self.history.record(ExchangeRecord(
                goal=request.goal,
                category=request.category,
                model=model_cfg.model,
                context_tokens=len(request.context.split()) * 4 // 3,
                context_preview=request.context[:2000],
                sources=json.dumps([]),
                images_count=len(request.images) if request.images else 0,
                action_type=action.action_type,
                content=action.content[:5000],
                confidence=action.confidence,
                target_path=action.target_path,
                affected_files=json.dumps(action.affected_files),
                tokens_used=action.tokens_used,
                duration_s=duration,
                status=status,
                error_message=error,
            ))
        except Exception as e:
            logger.warning(f"Failed to record exchange: {e}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
            "models": {k: v.model for k, v in self.config.models.items()},
        }
