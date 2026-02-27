"""Regression tests: prompt selection should follow real chunk categories.

Historically, ToonicServer built a legacy context string and LLMRouter wrapped it
into a single CODE chunk, which forced CodeAnalysisPrompt even for web monitoring.
"""

from toonic.server.llm.prompts import GenericPrompt, CodeAnalysisPrompt, select_prompt_builder
from toonic.server.models import SourceCategory


def test_web_category_selects_generic_prompt():
    builder = select_prompt_builder(goal="describe what you see", categories={SourceCategory.WEB})
    assert isinstance(builder, GenericPrompt)
    assert not isinstance(builder, CodeAnalysisPrompt)


def test_code_category_selects_code_analysis_prompt():
    builder = select_prompt_builder(goal="find bugs", categories={SourceCategory.CODE})
    assert isinstance(builder, CodeAnalysisPrompt)
