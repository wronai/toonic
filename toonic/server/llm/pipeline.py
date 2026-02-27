"""
LLM Pipeline — orchestrates prompt → model → call → parse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from toonic.server.models import ActionResponse, ContextChunk
from toonic.server.llm.prompts import PromptBuilder, GenericPrompt, select_prompt_builder
from toonic.server.llm.caller import LLMCaller
from toonic.server.llm.parser import ResponseParser

logger = logging.getLogger("toonic.llm.pipeline")


@dataclass
class LLMPipeline:
    """Orchestrates the full LLM flow: prompt → model → call → parse."""

    caller: LLMCaller
    parser: ResponseParser = field(default_factory=ResponseParser)
    prompt_builder: Optional[PromptBuilder] = None  # None = auto-select

    async def execute(
        self,
        goal: str,
        category: str,
        chunks: List[ContextChunk],
        images: Optional[List[str]] = None,
    ) -> ActionResponse:
        images = images or []

        # Stage 1: Select prompt strategy
        builder = self.prompt_builder
        if builder is None:
            categories = {c.category for c in chunks}
            builder = select_prompt_builder(goal, categories)
        logger.debug(f"Using prompt builder: {type(builder).__name__}")

        # Stage 2: Build prompt
        prompt = builder.build(goal=goal, chunks=chunks, images=images)

        # Stage 3: Select model
        model = self.caller.select_model(
            category=category,
            has_images=bool(prompt["images"]),
        )
        logger.info(f"LLM pipeline: model={model}, chunks={len(chunks)}, images={len(images)}")

        # Stage 4: Call LLM
        raw_response = await self.caller.call(
            model=model,
            system=prompt["system"],
            user=prompt["user"],
            images=prompt["images"] or None,
        )

        # Stage 5: Parse response
        result = self.parser.parse(raw_response, category)
        return result
