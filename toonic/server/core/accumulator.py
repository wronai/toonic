"""
Context Accumulator — manages token budget across data sources.

REFACTORED: priority-based eviction instead of pure LRU.
Backward-compatible API: update(), get_context(), get_stats().
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from toonic.server.models import ContextChunk, SourceCategory


@dataclass
class BudgetConfig:
    """Token budget configuration per category."""
    total_tokens: int = 100_000
    allocations: Dict[str, float] = field(default_factory=lambda: {
        "code": 0.40, "config": 0.05, "logs": 0.15,
        "video": 0.15, "audio": 0.10, "document": 0.05, "system": 0.10,
    })


class ContextAccumulator:
    """Manages context window for LLM — allocates token budget per category.

    REFACTORED: priority-based eviction instead of pure LRU.
    Backward-compatible API: update(), get_context(), get_stats().
    """

    def __init__(self, max_tokens: int = 100_000, allocation: Dict[str, float] | None = None,
                 config: BudgetConfig | None = None):
        if config:
            self.budget = config
        else:
            self.budget = BudgetConfig(
                total_tokens=max_tokens,
                allocations=allocation or {
                    "code": 0.40, "config": 0.05, "logs": 0.15,
                    "video": 0.15, "audio": 0.10, "document": 0.05, "system": 0.10,
                },
            )
        # Backward compat aliases
        self.max_tokens = self.budget.total_tokens
        self.allocation = self.budget.allocations
        # Per-category chunk lists (priority-sorted)
        self._cat_chunks: Dict[str, List[ContextChunk]] = defaultdict(list)
        # Also keep source_id → latest chunk for backward compat
        self._chunks: Dict[str, ContextChunk] = {}
        self._history: Dict[str, List[ContextChunk]] = defaultdict(list)
        self._lock = threading.Lock()

    def update(self, chunk: ContextChunk) -> None:
        """Add chunk. Evict lowest-priority if budget exceeded."""
        cat = chunk.category.value if isinstance(chunk.category, SourceCategory) else chunk.category
        with self._lock:
            # Maintain backward-compat source_id → chunk map
            if chunk.is_delta and chunk.source_id in self._chunks:
                old = self._chunks[chunk.source_id]
                self._history[chunk.source_id].append(old)
                if len(self._history[chunk.source_id]) > 10:
                    self._history[chunk.source_id] = self._history[chunk.source_id][-10:]
            self._chunks[chunk.source_id] = chunk
            # Also add to per-category list
            self._cat_chunks[cat].append(chunk)
            self._enforce_budget(cat)

    def get_context(self, goal: str = "", system_prompt: str = "") -> str:
        """Build full context string within token budget (backward-compatible)."""
        with self._lock:
            return self._build_context(goal, system_prompt)

    def get_chunks(
        self,
        categories: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[List[ContextChunk], List[str]]:
        """Return (chunks, images) sorted by priority within budget."""
        max_tokens = max_tokens or self.budget.total_tokens
        result_chunks: List[ContextChunk] = []
        result_images: List[str] = []

        with self._lock:
            for cat, chunks in self._cat_chunks.items():
                if categories and cat not in categories:
                    continue

                # Sort: highest priority + newest first
                sorted_chunks = sorted(
                    chunks,
                    key=lambda c: (getattr(c, 'priority', 0.5), c.timestamp),
                    reverse=True,
                )

                alloc = self.budget.allocations.get(cat, 0.10)
                cat_budget = int(max_tokens * alloc)
                cat_tokens = 0

                for chunk in sorted_chunks:
                    est = chunk.token_estimate or (len(chunk.toon_spec.split()) * 4 // 3 if chunk.toon_spec else 0)
                    if cat_tokens + est > cat_budget:
                        break
                    result_chunks.append(chunk)
                    # Collect base64 images
                    if chunk.raw_data and chunk.raw_encoding == "base64_jpeg":
                        import base64
                        result_images.append(base64.b64encode(chunk.raw_data).decode())
                    extra = chunk.metadata.get("extra_images_b64", [])
                    result_images.extend(extra)
                    cat_tokens += est

        # Return chronologically for context coherence
        result_chunks.sort(key=lambda c: c.timestamp)
        return result_chunks, result_images

    def _build_context(self, goal: str, system_prompt: str) -> str:
        """Assemble context respecting token allocation (backward compat)."""
        sections: Dict[str, List[str]] = defaultdict(list)

        for source_id, chunk in self._chunks.items():
            cat = chunk.category.value if isinstance(chunk.category, SourceCategory) else chunk.category
            sections[cat].append(chunk.toon_spec)

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
            est_tokens = len(combined.split()) * 4 // 3
            if est_tokens > budget:
                words = combined.split()
                combined = " ".join(words[:int(budget * 3 // 4)])
                combined += f"\n... [truncated, {est_tokens} tokens → {budget} budget]"
            parts.append(f"[{cat.upper()}]\n{combined}\n")

        return "\n".join(parts)

    def _enforce_budget(self, category: str) -> None:
        """Evict lowest-priority chunks when budget exceeded."""
        alloc = self.budget.allocations.get(category, 0.10)
        budget = int(self.budget.total_tokens * alloc)
        chunks = self._cat_chunks[category]
        total = sum(c.token_estimate or (len(c.toon_spec.split()) * 4 // 3 if c.toon_spec else 0) for c in chunks)

        if total <= budget:
            return

        # Sort: lowest priority + oldest → to evict
        chunks.sort(key=lambda c: (getattr(c, 'priority', 0.5), c.timestamp))

        while total > budget and chunks:
            evicted = chunks.pop(0)
            est = evicted.token_estimate or (len(evicted.toon_spec.split()) * 4 // 3 if evicted.toon_spec else 0)
            total -= est

    def get_stats(self) -> Dict[str, Any]:
        """Return accumulator statistics."""
        with self._lock:
            cat_counts = defaultdict(int)
            cat_tokens = defaultdict(int)
            for chunk in self._chunks.values():
                cat = chunk.category.value if isinstance(chunk.category, SourceCategory) else chunk.category
                cat_counts[cat] += 1
                cat_tokens[cat] += chunk.token_estimate
            stats = {
                "total_sources": len(self._chunks),
                "total_tokens": sum(cat_tokens.values()),
                "max_tokens": self.max_tokens,
                "per_category": {cat: {"sources": cat_counts[cat], "tokens": cat_tokens[cat]}
                                 for cat in cat_counts},
            }
            return stats

    def clear(self, category: Optional[str] = None) -> None:
        with self._lock:
            if category:
                self._cat_chunks.pop(category, None)
                # Also clean source_id map for this category
                to_remove = [sid for sid, c in self._chunks.items()
                             if (c.category.value if isinstance(c.category, SourceCategory) else c.category) == category]
                for sid in to_remove:
                    del self._chunks[sid]
                    self._history.pop(sid, None)
            else:
                self._chunks.clear()
                self._history.clear()
                self._cat_chunks.clear()
