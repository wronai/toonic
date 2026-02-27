"""
LLM Pipeline — modular prompt building, API calling, and response parsing.

Extracted from core/router.py for testability and extensibility.
"""

from toonic.server.llm.pipeline import LLMPipeline
from toonic.server.llm.prompts import (
    PromptBuilder,
    GenericPrompt,
    CodeAnalysisPrompt,
    CCTVEventPrompt,
    select_prompt_builder,
)
from toonic.server.llm.caller import LLMCaller
from toonic.server.llm.parser import ResponseParser

__all__ = [
    "LLMPipeline",
    "PromptBuilder",
    "GenericPrompt",
    "CodeAnalysisPrompt",
    "CCTVEventPrompt",
    "LLMCaller",
    "ResponseParser",
    "select_prompt_builder",
]
