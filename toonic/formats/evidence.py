"""
Evidence Graph — multimodal fusion
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from toonic.core.base import BaseHandlerMixin
from toonic.core.registry import FormatRegistry


# =============================================================================
# Evidence Node
# =============================================================================

@dataclass
class EvidenceNode:
    """Pojedynczy węzeł dowodowy w Evidence Graph."""
    id: str
    category: str
    timestamp_s: float = 0.0
    summary: str = ""
    confidence: float = 1.0

    lowq_data: str = ""
    lowq_size_bytes: int = 0

    source_path: str = ""
    byte_offset: int = 0
    byte_length: int = 0

    related_to: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Evidence Graph
# =============================================================================

@dataclass
class EvidenceGraph:
    """Multimodalny graf dowodowy — implementuje FileLogic Protocol."""
    source_file: str = "evidence_graph.toon"
    source_hash: str = ""
    file_category: str = "evidence"

    title: str = ""
    created_at: str = ""
    duration_s: float = 0.0
    num_sources: int = 0

    nodes: List[EvidenceNode] = field(default_factory=list)
    category_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    video_resolution: Tuple[int, int] = (160, 120)
    video_quality: int = 10
    audio_sample_rate: int = 8000
    audio_encoding: str = "ulaw"
    vad_aggressiveness: int = 2

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "duration_s": self.duration_s,
            "num_sources": self.num_sources,
            "total_nodes": len(self.nodes),
            "categories": {
                cat: len([n for n in self.nodes if n.category == cat])
                for cat in set(n.category for n in self.nodes)
            },
            "total_lowq_size": sum(n.lowq_size_bytes for n in self.nodes),
        }

    def complexity(self) -> int:
        return len(self.nodes) * 3 + self.num_sources * 5


# =============================================================================
# Evidence Graph Builder
# =============================================================================

class EvidenceGraphBuilder:
    """Buduje Evidence Graph z wielu źródeł."""

    def __init__(self):
        self.nodes: List[EvidenceNode] = []
        self.sources: List[str] = []

    def add_code_evidence(self, source_file: str, functions: List[Dict]) -> None:
        self.sources.append(source_file)
        for func in functions:
            self.nodes.append(EvidenceNode(
                id=f"code:{source_file}:{func.get('name', '?')}",
                category='code',
                summary=f"{func.get('name', '?')}{func.get('sig', '()')}",
                source_path=source_file,
                related_to=[],
            ))

    def add_document_evidence(self, source_file: str, sections: List[Dict]) -> None:
        self.sources.append(source_file)
        for i, section in enumerate(sections):
            self.nodes.append(EvidenceNode(
                id=f"doc:{source_file}:s{i}",
                category='document',
                summary=section.get('title', '') + ': ' + section.get('summary', ''),
                source_path=source_file,
            ))

    def add_video_evidence(self, source_file: str, keyframes: List[Dict]) -> None:
        self.sources.append(source_file)
        for kf in keyframes:
            self.nodes.append(EvidenceNode(
                id=f"video:{source_file}:{kf.get('ts', 0):.1f}s",
                category='video',
                timestamp_s=kf.get('ts', 0),
                summary=f"scene_change:{kf.get('score', 0):.2f}",
                lowq_data=kf.get('b64', '')[:100],
                lowq_size_bytes=kf.get('size', 0),
                source_path=source_file,
            ))

    def add_audio_evidence(self, source_file: str, speech_segments: List[Dict]) -> None:
        self.sources.append(source_file)
        for seg in speech_segments:
            self.nodes.append(EvidenceNode(
                id=f"audio:{source_file}:{seg.get('start', 0):.1f}s",
                category='audio',
                timestamp_s=seg.get('start', 0),
                summary=f"speech:{seg.get('duration', 0):.1f}s",
                lowq_data=seg.get('b64', '')[:100],
                lowq_size_bytes=seg.get('size', 0),
                source_path=source_file,
            ))

    def add_database_evidence(self, source_file: str, tables: List[Dict]) -> None:
        self.sources.append(source_file)
        for table in tables:
            cols = table.get('columns', [])
            col_summary = ', '.join(c.get('name', '') for c in cols[:5])
            self.nodes.append(EvidenceNode(
                id=f"db:{source_file}:{table.get('name', '?')}",
                category='database',
                summary=f"table:{table.get('name', '?')}({col_summary})",
                source_path=source_file,
            ))

    def add_test_evidence(self, source_file: str, results: Dict) -> None:
        self.sources.append(source_file)
        self.nodes.append(EvidenceNode(
            id=f"test:{source_file}",
            category='test',
            summary=f"tests:{results.get('total', 0)} "
                    f"pass:{results.get('passed', 0)} "
                    f"fail:{results.get('failed', 0)}",
            source_path=source_file,
        ))

    def build(self, title: str = "") -> EvidenceGraph:
        self._auto_link_relations()

        stats: Dict[str, Dict] = {}
        for node in self.nodes:
            cat = node.category
            if cat not in stats:
                stats[cat] = {'count': 0, 'total_size': 0}
            stats[cat]['count'] += 1
            stats[cat]['total_size'] += node.lowq_size_bytes

        total_duration = max(
            (n.timestamp_s for n in self.nodes if n.timestamp_s > 0),
            default=0,
        )

        return EvidenceGraph(
            title=title or "Evidence Graph",
            source_hash=hashlib.sha256(
                '|'.join(sorted(set(self.sources))).encode()
            ).hexdigest()[:16],
            duration_s=total_duration,
            num_sources=len(set(self.sources)),
            nodes=self.nodes,
            category_stats=stats,
        )

    def _auto_link_relations(self) -> None:
        by_source: Dict[str, List[int]] = {}
        for i, node in enumerate(self.nodes):
            by_source.setdefault(node.source_path, []).append(i)

        for source, indices in by_source.items():
            for i in indices:
                for j in indices:
                    if i != j:
                        self.nodes[i].related_to.append(self.nodes[j].id)

        timestamped = [(i, n) for i, n in enumerate(self.nodes) if n.timestamp_s > 0]
        for i, (idx_a, node_a) in enumerate(timestamped):
            for idx_b, node_b in timestamped[i+1:]:
                if abs(node_a.timestamp_s - node_b.timestamp_s) <= 5.0:
                    node_a.related_to.append(node_b.id)
                    node_b.related_to.append(node_a.id)


# =============================================================================
# Evidence Graph Handler
# =============================================================================

class EvidenceGraphHandler(BaseHandlerMixin):
    """Handler dla Evidence Graph."""

    extensions = frozenset({'.evidence.toon', '.eg.toon'})
    category = 'evidence'
    requires = ()

    def parse(self, path: Path) -> EvidenceGraph:
        content = path.read_text(errors='replace')
        return EvidenceGraph(
            source_file=path.name,
            source_hash=self._compute_hash(path),
            metadata={'raw_content': content[:500]},
        )

    def to_spec(self, logic: EvidenceGraph, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            return self._to_toon(logic)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def _to_toon(self, eg: EvidenceGraph) -> str:
        total_lowq = sum(n.lowq_size_bytes for n in eg.nodes)
        categories = {}
        for n in eg.nodes:
            categories.setdefault(n.category, []).append(n)

        lines = [
            f"# {eg.source_file} | {eg.num_sources} sources | {len(eg.nodes)} nodes",
            f"# {' | '.join(f'{cat}:{len(nodes)}' for cat, nodes in categories.items())}",
            f"# total_lowq: {total_lowq/1024:.1f}kB | duration: {eg.duration_s:.0f}s",
            "",
        ]

        for cat, nodes in categories.items():
            lines.append(f"[{cat.upper()}] {len(nodes)} nodes:")
            for n in nodes[:20]:
                parts = [f"  {n.id}"]
                if n.summary:
                    parts.append(n.summary)
                if n.lowq_size_bytes:
                    parts.append(f"{n.lowq_size_bytes/1024:.1f}kB")
                lines.append(" | ".join(parts))
            if len(nodes) > 20:
                lines.append(f"  ... +{len(nodes)-20} more")
            lines.append("")

        all_relations = []
        for n in eg.nodes:
            for rel_id in n.related_to[:3]:
                all_relations.append(f"  {n.id} -> {rel_id}")

        if all_relations:
            lines.append(f"[RELATIONS] {len(all_relations)} links:")
            for rel in all_relations[:20]:
                lines.append(rel)
            if len(all_relations) > 20:
                lines.append(f"  ... +{len(all_relations)-20} more")

        return '\n'.join(lines)

    def reproduce(self, logic: EvidenceGraph, client: Any = None, target_fmt: str | None = None) -> str:
        return f"# Evidence Graph: {logic.title}\n# {len(logic.nodes)} nodes, read-only"

    def sniff(self, path: Path, content: str) -> float:
        if 'evidence' in path.name.lower():
            return 0.9
        if '[CODE]' in content and '[VIDEO]' in content:
            return 0.7
        return 0.0


# =============================================================================
# Rejestracja
# =============================================================================

def register_evidence_handlers() -> None:
    FormatRegistry.register(EvidenceGraphHandler())
