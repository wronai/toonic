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
from toonic.server.core.history import ConversationHistory, ExchangeRecord

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

    def __init__(self, config: ServerConfig, history: Optional['ConversationHistory'] = None):
        self.config = config
        self.history = history
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
            model_cfg = ModelConfig(
                provider=model_cfg.provider,
                model=request.model_override,
                max_tokens=model_cfg.max_tokens,
                supports=model_cfg.supports,
                api_key_env=model_cfg.api_key_env,
                base_url=model_cfg.base_url,
            )

        try:
            response_text, tokens_used = await self._call_llm(model_cfg, request)
            self._total_requests += 1
            duration = time.time() - start

            action = self._parse_response(response_text)
            action.model_used = self._litellm_model_id(model_cfg)
            action.tokens_used = int(tokens_used or 0)
            action.duration_s = duration
            action.action_id = f"action-{self._total_requests}"

            self._record_exchange(request, action, model_cfg, duration, "ok")
            return action

        except Exception as e:
            logger.error(f"LLM error ({self._litellm_model_id(model_cfg)}): {e}")
            msg = str(e)
            if "LLM Provider NOT provided" in msg:
                msg = (
                    f"{msg}\n\n"
                    "To fix: set LLM_PROVIDER (e.g. 'openrouter') or pass a provider-qualified model. "
                    "Examples: 'openrouter/google/gemini-2.5-flash-preview' or set LLM_PROVIDER=openrouter "
                    "with LLM_MODEL='google/gemini-2.5-flash-preview'."
                )
            action = ActionResponse(
                action_type="error",
                content=f"LLM error: {msg}",
                model_used=self._litellm_model_id(model_cfg),
                tokens_used=0,
                duration_s=time.time() - start,
            )
            self._record_exchange(request, action, model_cfg, time.time() - start, "error", msg)
            return action

    def _litellm_model_id(self, model_cfg: ModelConfig) -> str:
        """Return provider-qualified LiteLLM model id.

        LiteLLM typically expects '<provider>/<model>'. In our config, `model_cfg.model`
        may be just a provider-native id (e.g. 'google/gemini-...'), so we prefix
        `model_cfg.provider` unless the model already starts with '<provider>/'.
        """
        model = (model_cfg.model or "").strip()
        provider = (model_cfg.provider or "").strip()
        if not model:
            return model
        if provider and model.startswith(provider + "/"):
            return model
        if provider:
            return f"{provider}/{model}"
        return model

    async def _call_llm(self, model_cfg: ModelConfig, request: LLMRequest) -> tuple[str, int]:
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
                for img_b64 in request.images[:8]:  # max 8 images (frames + ROI + diff)
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    })
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": request.context})

            api_key = os.environ.get("LLM_API_KEY",
                      os.environ.get(model_cfg.api_key_env,
                      os.environ.get("OPENROUTER_API_KEY", "")))
            base_url = model_cfg.base_url or os.environ.get("LLM_BASE_URL", "")

            model_id = self._litellm_model_id(model_cfg)
            response = await litellm.acompletion(
                model=model_id,
                messages=messages,
                max_tokens=model_cfg.max_tokens,
                api_key=api_key or None,
                base_url=base_url or None,
            )

            text = response.choices[0].message.content
            tokens = int(getattr(getattr(response, "usage", None), "total_tokens", 0) or 0)
            self._total_tokens += tokens
            return text, tokens

        except ImportError:
            logger.warning("litellm not installed — using mock response")
            text = self._mock_response(request)
            tokens = len(text.split()) * 4 // 3
            return text, tokens

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
        base = (
            "You are Toonic, an AI assistant that analyzes projects and data streams.\n"
            "You receive context in TOON format (Token-Oriented Object Notation) — "
            "a compact representation of code, documents, configs, logs, and multimedia.\n\n"
            f"Current goal: {goal}\n\n"
        )
        # Event-focused instructions for video/CCTV analysis
        video_instructions = (
            "VIDEO/CCTV ANALYSIS INSTRUCTIONS:\n"
            "- You may receive multiple images: sequential event frames, ROI crops of detected objects, "
            "and a motion-diff overlay (last image, red areas = changed pixels).\n"
            "- Focus on EVENTS and ACTIONS: describe what is happening, not static scene appearance.\n"
            "- Compare frames: note movement direction, speed, appearing/disappearing objects.\n"
            "- For detected objects (person, car, etc.): describe their actions, trajectory, "
            "interactions — not just their presence.\n"
            "- ROI crops show close-ups of detected objects — use them for detail (clothing, "
            "vehicle type, behavior).\n"
            "- If diff overlay is present: focus analysis on red-highlighted areas (motion regions).\n"
            "- Classify events: normal_activity, suspicious, intrusion, vehicle_entry, "
            "package_delivery, animal, weather_change, equipment_fault.\n"
            "- Include temporal context: 'person entered from left', 'car stopped at gate'.\n\n"
        )
        response_format = (
            "Respond with a JSON object:\n"
            '{"action": "report|code_fix|alert|none", '
            '"content": "your analysis or fix", '
            '"target_path": "file to modify (if code_fix)", '
            '"confidence": 0.0-1.0, '
            '"affected_files": ["list", "of", "files"]}'
        )
        # Include video instructions when goal hints at monitoring/video
        goal_lower = goal.lower()
        if any(kw in goal_lower for kw in (
            "video", "monitor", "cctv", "security", "surveillance", "camera",
            "detect", "watch", "frame", "stream", "rtsp",
        )):
            return base + video_instructions + response_format
        return base + response_format

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
