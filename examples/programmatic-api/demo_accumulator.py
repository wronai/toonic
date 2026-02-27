#!/usr/bin/env python3
"""
Demo: ContextAccumulator with priority-based eviction.

Shows how high-priority chunks (CRITICAL/ERROR logs) survive eviction
while low-priority chunks (INFO/DEBUG) are dropped when budget is tight.

Usage:
    python examples/programmatic-api/demo_accumulator.py
"""

from toonic.server.core.accumulator import ContextAccumulator, BudgetConfig
from toonic.server.models import ContextChunk, SourceCategory, ContentType


def main():
    print("=" * 60)
    print("Demo: Priority-Based Context Accumulator")
    print("=" * 60)

    # Small budget to demonstrate eviction
    acc = ContextAccumulator(config=BudgetConfig(
        total_tokens=500,
        allocations={"code": 0.30, "logs": 0.50, "video": 0.10, "system": 0.10},
    ))

    # Add chunks with different priorities
    chunks_to_add = [
        ("info-1", SourceCategory.LOGS, "2025-01-15 INFO [api] GET /health → 200 OK (12ms)", ContentType.LOG_ENTRIES, 0.3),
        ("info-2", SourceCategory.LOGS, "2025-01-15 INFO [api] GET /users → 200 OK (45ms)", ContentType.LOG_ENTRIES, 0.3),
        ("info-3", SourceCategory.LOGS, "2025-01-15 INFO [cache] Hit rate: 94%", ContentType.LOG_ENTRIES, 0.3),
        ("warn-1", SourceCategory.LOGS, "2025-01-15 WARNING [db] Slow query: 1200ms SELECT * FROM orders", ContentType.LOG_ENTRIES, 0.5),
        ("error-1", SourceCategory.LOGS, "2025-01-15 ERROR [db] Connection pool exhausted — 0/100 available", ContentType.LOG_ENTRIES, 0.8),
        ("critical-1", SourceCategory.LOGS, "2025-01-15 CRITICAL [db] Replication lag 15s — threshold 5s", ContentType.LOG_ENTRIES, 1.0),
        ("code-1", SourceCategory.CODE, "M app.py | c UserService | m get_user(id) | m delete_user(id)", ContentType.TOON_SPEC, 0.5),
        ("info-4", SourceCategory.LOGS, "2025-01-15 INFO [api] POST /login → 200 OK (230ms)", ContentType.LOG_ENTRIES, 0.3),
        ("info-5", SourceCategory.LOGS, "2025-01-15 INFO [worker] Processed 42 jobs in batch", ContentType.LOG_ENTRIES, 0.3),
        ("error-2", SourceCategory.LOGS, "2025-01-15 ERROR [auth] Failed login for user admin from 10.0.0.1", ContentType.LOG_ENTRIES, 0.8),
    ]

    print(f"\nAdding {len(chunks_to_add)} chunks (budget: 500 tokens, logs=50%)...\n")

    for sid, cat, spec, ctype, pri in chunks_to_add:
        acc.update(ContextChunk(
            source_id=sid,
            category=cat,
            toon_spec=spec,
            content_type=ctype,
            priority=pri,
        ))

    # Show what survived eviction
    print("Chunks that survived (priority-sorted):")
    print("-" * 60)

    chunks, images = acc.get_chunks()
    for c in chunks:
        cat = c.category.value if hasattr(c.category, "value") else c.category
        pri_label = {1.0: "CRITICAL", 0.8: "ERROR", 0.5: "NORMAL", 0.3: "LOW", 0.1: "TRACE"}.get(c.priority, f"{c.priority:.1f}")
        print(f"  [{cat:5s}] pri={c.priority:.1f} ({pri_label:8s}) {c.toon_spec[:55]}")

    print(f"\nTotal chunks retained: {len(chunks)}")
    print(f"Images: {len(images)}")

    # Show stats
    stats = acc.get_stats()
    print(f"\nAccumulator stats:")
    print(f"  Total sources: {stats['total_sources']}")
    print(f"  Total tokens:  {stats['total_tokens']}")
    print(f"  Max tokens:    {stats['max_tokens']}")
    for cat, info in stats.get("per_category", {}).items():
        print(f"  [{cat}] {info['sources']} sources, {info['tokens']} tokens")

    # Show context string (backward compat)
    print(f"\nLegacy context string (first 300 chars):")
    print("-" * 60)
    ctx = acc.get_context(goal="analyze database connection issues")
    print(ctx[:300])
    print("...")

    print("\n" + "=" * 60)
    print("Key insight: CRITICAL and ERROR chunks survive eviction,")
    print("while INFO chunks are dropped when budget is tight.")
    print("=" * 60)


if __name__ == "__main__":
    main()
