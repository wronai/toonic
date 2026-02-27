#!/usr/bin/env python3
"""
Demo: LLM Pipeline — prompt building, model selection, and response parsing.

Uses mock mode (no API key needed) to show the full pipeline flow.

Usage:
    python examples/programmatic-api/demo_pipeline.py
"""

import asyncio

from toonic.server.llm.caller import LLMCaller
from toonic.server.llm.parser import ResponseParser
from toonic.server.llm.pipeline import LLMPipeline
from toonic.server.llm.prompts import (
    CCTVEventPrompt,
    CodeAnalysisPrompt,
    GenericPrompt,
    select_prompt_builder,
)
from toonic.server.models import ActionResponse, ContextChunk, ContentType, SourceCategory


def demo_prompt_selection():
    """Show how prompt builders are auto-selected."""
    print("=" * 60)
    print("1. Prompt Builder Auto-Selection")
    print("=" * 60)

    cases = [
        ("find bugs in the code", {SourceCategory.CODE}),
        ("CCTV security: detect intrusions", {SourceCategory.VIDEO}),
        ("monitor camera for suspicious activity", {SourceCategory.VIDEO}),
        ("summarize the dataset", {SourceCategory.DATA}),
        ("analyze code quality and log errors", {SourceCategory.CODE, SourceCategory.LOGS}),
    ]

    for goal, cats in cases:
        builder = select_prompt_builder(goal, cats)
        cat_names = ", ".join(c.value for c in cats)
        print(f"  goal={goal!r:50s} cats=[{cat_names}] → {type(builder).__name__}")


def demo_prompt_building():
    """Show what each prompt builder produces."""
    print("\n" + "=" * 60)
    print("2. Prompt Building")
    print("=" * 60)

    chunks = [
        ContextChunk(
            source_id="app.py",
            category=SourceCategory.CODE,
            toon_spec="M app.py | c UserService | m get_user(id) → User | m delete_user(id) → bool",
            content_type=ContentType.TOON_SPEC,
        ),
    ]

    builders = [
        ("GenericPrompt", GenericPrompt()),
        ("CodeAnalysisPrompt", CodeAnalysisPrompt()),
    ]

    for name, builder in builders:
        prompt = builder.build(goal="find bugs", chunks=chunks, images=[])
        print(f"\n  --- {name} ---")
        print(f"  System ({len(prompt['system'])} chars): {prompt['system'][:100]}...")
        print(f"  User ({len(prompt['user'])} chars): {prompt['user'][:100]}...")
        print(f"  Images: {len(prompt['images'])}")


def demo_response_parser():
    """Show response parsing from different formats."""
    print("\n" + "=" * 60)
    print("3. Response Parser")
    print("=" * 60)

    parser = ResponseParser()

    # JSON in markdown fence (wrapped in dict as LLMCaller returns)
    raw_json = {"content": '```json\n{"action": "alert", "content": "Hardcoded API key in config.py:15", "confidence": 0.95, "affected_files": ["config.py"]}\n```', "model": "test-model"}
    result = parser.parse(raw_json, "code")
    print(f"\n  JSON in fence → action={result.action_type}, confidence={result.confidence}, content={result.content[:50]}")

    # Plain JSON
    raw_plain = {"content": '{"action": "report", "content": "No issues found", "confidence": 0.8}', "model": "test-model"}
    result = parser.parse(raw_plain, "code")
    print(f"  Plain JSON   → action={result.action_type}, confidence={result.confidence}, content={result.content[:50]}")

    # Plain text fallback
    raw_text = {"content": "The code looks clean. No major issues detected.", "model": "test-model"}
    result = parser.parse(raw_text, "code")
    print(f"  Plain text   → action={result.action_type}, confidence={result.confidence}, content={result.content[:50]}")

    # Error response
    raw_error = {"error": "API timeout", "model": "test-model"}
    result = parser.parse(raw_error, "code")
    print(f"  Error resp   → action={result.action_type}, confidence={result.confidence}, content={result.content[:50]}")

    # Also show parse_raw_to_dict for direct string parsing
    print("\n  parse_raw_to_dict (direct string → dict):")
    d = parser.parse_raw_to_dict('{"action": "alert", "severity": "high"}')
    print(f"    Parsed: {d}")


async def demo_pipeline():
    """Show full pipeline execution in mock mode."""
    print("\n" + "=" * 60)
    print("4. Full Pipeline Execution (mock mode)")
    print("=" * 60)

    # api_key="" forces mock mode (no real API calls)
    pipeline = LLMPipeline(
        caller=LLMCaller(api_key="", model_map={}),
        parser=ResponseParser(),
    )

    # Code analysis
    code_chunks = [
        ContextChunk(
            source_id="main.py",
            category=SourceCategory.CODE,
            toon_spec="M main.py | c App | m run() | m handle_request(req)",
            content_type=ContentType.TOON_SPEC,
            priority=0.5,
        ),
    ]

    print("\n  Running pipeline: code analysis...")
    result = await pipeline.execute(
        goal="find bugs in request handling",
        category="code",
        chunks=code_chunks,
    )
    print(f"  → action={result.action_type}, confidence={result.confidence}")
    print(f"  → content: {result.content[:100]}")

    # Log analysis
    log_chunks = [
        ContextChunk(
            source_id="app.log",
            category=SourceCategory.LOGS,
            toon_spec="2025-01-15 ERROR [db] Connection refused\n2025-01-15 CRITICAL [db] Pool exhausted",
            content_type=ContentType.LOG_ENTRIES,
            priority=0.9,
        ),
    ]

    print("\n  Running pipeline: log analysis...")
    result = await pipeline.execute(
        goal="analyze database errors",
        category="logs",
        chunks=log_chunks,
    )
    print(f"  → action={result.action_type}, confidence={result.confidence}")
    print(f"  → content: {result.content[:100]}")


def main():
    demo_prompt_selection()
    demo_prompt_building()
    demo_response_parser()
    asyncio.run(demo_pipeline())

    print("\n" + "=" * 60)
    print("All demos completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
