"""
Context Accumulator — manages token budget across data sources.

Maintains a ring buffer of ContextChunks with priority-based eviction.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

from toonic.server.models import ContextChunk, SourceCategory


class ContextAccumulator:
    """Manages context window for LLM — allocates token budget per category."""

    def __init__(self, max_tokens: int = 100_000, allocation: Dict[str, float] | None = None):
        self.max_tokens = max_tokens
        self.allocation = allocation or {
            "code": 0.40, "config": 0.05, "logs": 0.15,
            "video": 0.15, "audio": 0.10, "document": 0.05, "system": 0.10,
        }
        self._chunks: Dict[str, ContextChunk] = {}   # source_id → latest chunk
        self._history: Dict[str, List[ContextChunk]] = defaultdict(list)
        self._lock = threading.Lock()

    def update(self, chunk: ContextChunk) -> None:
        """Add or replace a context chunk."""
        with self._lock:
            if chunk.is_delta and chunk.source_id in self._chunks:
                old = self._chunks[chunk.source_id]
                self._history[chunk.source_id].append(old)
                # Keep only last 10 deltas per source
                if len(self._history[chunk.source_id]) > 10:
                    self._history[chunk.source_id] = self._history[chunk.source_id][-10:]
            self._chunks[chunk.source_id] = chunk

    def get_context(self, goal: str = "", system_prompt: str = "") -> str:
        """Build full context string within token budget."""
        with self._lock:
            return self._build_context(goal, system_prompt)

    def _build_context(self, goal: str, system_prompt: str) -> str:
        """Assemble context respecting token allocation."""
        sections: Dict[str, List[str]] = defaultdict(list)

        for source_id, chunk in self._chunks.items():
            cat = chunk.category.value if isinstance(chunk.category, SourceCategory) else chunk.category
            sections[cat].append(chunk.toon_spec)

        # Build with budget
        parts = []
        if system_prompt:
            parts.append(f"[SYSTEM]\n{system_prompt}\n")
        if goal:
            parts.append(f"[GOAL]\n{goal}\n")

        for cat, alloc in sorted(self.allocation.items(), key=lambda x: -x[1]):
            if cat == "system":
                continue
            cat_specs = sections.get(cat, [])
            if not cat_specs:
                continue
            budget = int(self.max_tokens * alloc)
            combined = "\n".join(cat_specs)
            # Rough truncation by estimated tokens
            est_tokens = len(combined.split()) * 4 // 3
            if est_tokens > budget:
                words = combined.split()
                combined = " ".join(words[:int(budget * 3 // 4)])
                combined += f"\n... [truncated, {est_tokens} tokens → {budget} budget]"
            parts.append(f"[{cat.upper()}]\n{combined}\n")

        return "\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        """Return accumulator statistics."""
        with self._lock:
            cat_counts = defaultdict(int)
            cat_tokens = defaultdict(int)
            for chunk in self._chunks.values():
                cat = chunk.category.value if isinstance(chunk.category, SourceCategory) else chunk.category
                cat_counts[cat] += 1
                cat_tokens[cat] += chunk.token_estimate
            return {
                "total_sources": len(self._chunks),
                "total_tokens": sum(cat_tokens.values()),
                "max_tokens": self.max_tokens,
                "per_category": {cat: {"sources": cat_counts[cat], "tokens": cat_tokens[cat]}
                                 for cat in cat_counts},
            }

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._history.clear()
