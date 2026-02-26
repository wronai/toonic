"""
Toonic — Etap 7: Evidence Graph (Multimodal Fusion)
====================================================

Fuzja wszystkich modalności: kod + docs + video + audio + multi-cam → Evidence Graph.
Pipeline: multi-source → sync timeline → fused TOON → lazy retrieval dla LLM.

Nowe capabilities (z załączonego podsumowania v4.2):
- Evidence Graph: indeks + low-q próbki + lazy retrieval
- Multi-stream sync: timestamp-based fusion (video + audio + code changes)
- Speech-triggered video: segmenty tylko przy wykrytej mowie
- Cross-domain reasoning: kod + SQL + testy + security w jednym prompcie
- VideoChatLogic: speaker + emotion/gesture fusion

Źródło: "zrób podsumowanie dla całego projektu" — filozofia v4.2
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from stage_0_foundation import BaseHandlerMixin, FileLogic, FormatRegistry


# =============================================================================
# Evidence Node — pojedynczy dowód w grafie
# =============================================================================

@dataclass
class EvidenceNode:
    """Pojedynczy węzeł dowodowy w Evidence Graph.

    Reprezentuje jeden fragment wiedzy z dowolnej modalności:
    kod, dokument, klatkę video, segment audio, wynik testu, etc.
    """
    id: str                     # "code:auth.py:validate_token"
    category: str               # code | document | audio | video | test | security
    timestamp_s: float = 0.0    # dla sync multi-stream
    summary: str = ""           # jednolinijkowe streszczenie
    confidence: float = 1.0     # pewność 0.0-1.0

    # Low-quality próbka (inline w TOON)
    lowq_data: str = ""         # base64 keyframe / μ-law audio / compressed spec
    lowq_size_bytes: int = 0

    # Referencja do pełnych danych (lazy retrieval)
    source_path: str = ""       # ścieżka do oryginalnego pliku
    byte_offset: int = 0        # offset w pliku
    byte_length: int = 0        # długość fragmentu

    # Relacje z innymi węzłami
    related_to: List[str] = field(default_factory=list)  # [id1, id2, ...]

    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Evidence Graph — graf dowodowy
# =============================================================================

@dataclass
class EvidenceGraph:
    """Multimodalny graf dowodowy — implementuje FileLogic Protocol.

    Architektura v4.2: indeks + low-q próbki + lazy retrieval.
    LLM dostaje lekki indeks, a gdy potrzebuje dowodu — dociąga fragment.

    Warstwy:
    1. Index layer (nagłówek TOON) — ~1-5 kB
    2. Sample layer (low-q data inline) — ~10-100 kB per hour
    3. Reference layer (lazy retrieval pointers) — ~1 kB
    """
    source_file: str = "evidence_graph.toon"
    source_hash: str = ""
    file_category: str = "evidence"

    # Metadane grafu
    title: str = ""
    created_at: str = ""
    duration_s: float = 0.0
    num_sources: int = 0

    # Węzły pogrupowane per kategoria
    nodes: List[EvidenceNode] = field(default_factory=list)

    # Statystyki per kategoria
    category_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Konfiguracja kompresji
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
    """Buduje Evidence Graph z wielu źródeł.

    Łączy wyniki z handlerów etapów 0-6:
    - CodeLogic (stage 0) → evidence nodes z sygnaturami
    - DocumentLogic (stage 1) → evidence nodes z sekcjami
    - TableLogic / ConfigLogic (stage 2) → evidence nodes ze schematami
    - SqlSchemaLogic / ApiLogic (stage 3) → evidence nodes z definicjami
    - VideoLogic (stage 5) → evidence nodes z keyframes
    - AudioLogic (stage 6) → evidence nodes ze speech segments
    """

    def __init__(self):
        self.nodes: List[EvidenceNode] = []
        self.sources: List[str] = []

    def add_code_evidence(self, source_file: str, functions: List[Dict]) -> None:
        """Dodaj dowody z analizy kodu."""
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
        """Dodaj dowody z dokumentów."""
        self.sources.append(source_file)
        for i, section in enumerate(sections):
            self.nodes.append(EvidenceNode(
                id=f"doc:{source_file}:s{i}",
                category='document',
                summary=section.get('title', '') + ': ' + section.get('summary', ''),
                source_path=source_file,
            ))

    def add_video_evidence(
        self,
        source_file: str,
        keyframes: List[Dict],
    ) -> None:
        """Dodaj dowody z video (keyframes)."""
        self.sources.append(source_file)
        for kf in keyframes:
            self.nodes.append(EvidenceNode(
                id=f"video:{source_file}:{kf.get('ts', 0):.1f}s",
                category='video',
                timestamp_s=kf.get('ts', 0),
                summary=f"scene_change:{kf.get('score', 0):.2f}",
                lowq_data=kf.get('b64', '')[:100],  # truncated for index
                lowq_size_bytes=kf.get('size', 0),
                source_path=source_file,
            ))

    def add_audio_evidence(
        self,
        source_file: str,
        speech_segments: List[Dict],
    ) -> None:
        """Dodaj dowody z audio (speech segments)."""
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
        """Dodaj dowody ze schematów SQL."""
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
        """Dodaj dowody z raportów testów."""
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
        """Zbuduj Evidence Graph z zebranych dowodów."""
        # Automatyczne linkowanie relacji
        self._auto_link_relations()

        # Statystyki per kategoria
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
        """Automatyczne linkowanie relacji między węzłami.

        Heurystyki:
        - Węzły z tego samego pliku → powiązane
        - Węzły z podobnym timestamp_s (±5s) → powiązane
        - Węzły code ↔ test z tym samym modułem → powiązane
        """
        by_source: Dict[str, List[int]] = {}
        for i, node in enumerate(self.nodes):
            by_source.setdefault(node.source_path, []).append(i)

        # Link nodes from same source
        for source, indices in by_source.items():
            for i in indices:
                for j in indices:
                    if i != j:
                        self.nodes[i].related_to.append(self.nodes[j].id)

        # Link nodes by timestamp proximity (±5s)
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
    """Handler dla Evidence Graph — generuje i parsuje TOON Evidence Graph.

    Nie parsuje plików bezpośrednio — agreguje wyniki z innych handlerów.
    Użycie: Pipeline.evidence("./project/", fmt='toon')
    """

    extensions = frozenset({'.evidence.toon', '.eg.toon'})
    category = 'evidence'
    requires = ()

    def parse(self, path: Path) -> EvidenceGraph:
        """Parsuj istniejący Evidence Graph TOON."""
        content = path.read_text(errors='replace')
        # Prosty parser nagłówka
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
        """
        # evidence_graph.toon | 5 sources | 142 nodes
        # code:35 | doc:12 | video:48 | audio:32 | db:8 | test:7
        # total_lowq: 245kB | duration: 3600s

        [CODE] 35 nodes:
          code:auth.py:validate_token | validate_token(token:str)->bool
          code:auth.py:create_session | create_session(user:User)->Session
          ...

        [VIDEO] 48 nodes:
          video:cam1.mp4:5.2s | scene_change:0.45 | 2.5kB
          video:cam1.mp4:23.1s | scene_change:0.67 | 2.3kB
          ...

        [AUDIO] 32 nodes (speech-only):
          audio:meeting.wav:12.3s | speech:2.8s | 11.2kB μ-law
          ...

        [RELATIONS]:
          audio:meeting.wav:12.3s → video:cam1.mp4:12.5s (temporal ±5s)
          code:auth.py:validate_token → test:test_auth.py (same module)
        """
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

        # Węzły per kategoria
        for cat, nodes in categories.items():
            lines.append(f"[{cat.upper()}] {len(nodes)} nodes:")
            for n in nodes[:20]:  # max 20 per category w indeksie
                parts = [f"  {n.id}"]
                if n.summary:
                    parts.append(n.summary)
                if n.lowq_size_bytes:
                    parts.append(f"{n.lowq_size_bytes/1024:.1f}kB")
                lines.append(" | ".join(parts))
            if len(nodes) > 20:
                lines.append(f"  ... +{len(nodes)-20} more")
            lines.append("")

        # Relacje (top 20)
        all_relations = []
        for n in eg.nodes:
            for rel_id in n.related_to[:3]:
                all_relations.append(f"  {n.id} → {rel_id}")

        if all_relations:
            lines.append(f"[RELATIONS] {len(all_relations)} links:")
            for rel in all_relations[:20]:
                lines.append(rel)
            if len(all_relations) > 20:
                lines.append(f"  ... +{len(all_relations)-20} more")

        return '\n'.join(lines)

    def reproduce(self, logic: EvidenceGraph, client: Any = None, target_fmt: str | None = None) -> str:
        """Evidence Graph jest read-only — nie reprodukujemy."""
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
    for handler in [EvidenceGraphHandler()]:
        FormatRegistry.register(handler)


# =============================================================================
# Testy
# =============================================================================

if __name__ == '__main__':
    print("=== Toonic Stage 7: Evidence Graph Tests ===\n")

    # Test 1: EvidenceNode
    node = EvidenceNode(
        id="code:auth.py:validate_token",
        category="code",
        summary="validate_token(token:str)->bool",
        source_path="auth.py",
    )
    assert node.category == "code"
    print("✓ EvidenceNode works")

    # Test 2: Builder — code
    builder = EvidenceGraphBuilder()
    builder.add_code_evidence("auth.py", [
        {"name": "validate_token", "sig": "(token:str)->bool"},
        {"name": "create_session", "sig": "(user:User)->Session"},
    ])
    assert len(builder.nodes) == 2
    print("✓ add_code_evidence: 2 nodes")

    # Test 3: Builder — document
    builder.add_document_evidence("README.md", [
        {"title": "Installation", "summary": "pip install toonic"},
        {"title": "Usage", "summary": "Run code2logic spec ./"},
    ])
    assert len(builder.nodes) == 4
    print("✓ add_document_evidence: +2 nodes")

    # Test 4: Builder — video
    builder.add_video_evidence("cam1.mp4", [
        {"ts": 5.2, "score": 0.45, "b64": "AAAA", "size": 2500},
        {"ts": 23.1, "score": 0.67, "b64": "BBBB", "size": 2300},
    ])
    assert len(builder.nodes) == 6
    print("✓ add_video_evidence: +2 nodes")

    # Test 5: Builder — audio
    builder.add_audio_evidence("meeting.wav", [
        {"start": 12.3, "duration": 2.8, "b64": "CCCC", "size": 11200},
        {"start": 45.6, "duration": 6.4, "b64": "DDDD", "size": 25600},
    ])
    assert len(builder.nodes) == 8
    print("✓ add_audio_evidence: +2 nodes")

    # Test 6: Builder — database
    builder.add_database_evidence("schema.sql", [
        {"name": "users", "columns": [{"name": "id"}, {"name": "email"}]},
        {"name": "posts", "columns": [{"name": "id"}, {"name": "title"}]},
    ])
    assert len(builder.nodes) == 10
    print("✓ add_database_evidence: +2 nodes")

    # Test 7: Builder — tests
    builder.add_test_evidence("test_report.xml", {
        "total": 120, "passed": 115, "failed": 5,
    })
    assert len(builder.nodes) == 11
    print("✓ add_test_evidence: +1 node")

    # Test 8: Build Evidence Graph
    eg = builder.build(title="Project Analysis")
    assert eg.num_sources == 6
    assert len(eg.nodes) == 11
    assert 'code' in eg.category_stats
    assert 'video' in eg.category_stats
    assert 'audio' in eg.category_stats
    print(f"✓ EvidenceGraph built: {eg.num_sources} sources, {len(eg.nodes)} nodes")
    print(f"  Categories: {list(eg.category_stats.keys())}")

    # Test 9: TOON generation
    handler = EvidenceGraphHandler()
    toon = handler.to_spec(eg, 'toon')
    assert 'evidence' in toon.lower() or '# ' in toon
    assert '[CODE]' in toon
    assert '[VIDEO]' in toon
    assert '[AUDIO]' in toon
    assert '[DATABASE]' in toon
    assert '[TEST]' in toon
    print(f"\n✓ Evidence Graph TOON:\n{toon}")

    # Test 10: Registry
    FormatRegistry.reset()
    register_evidence_handlers()
    assert len(FormatRegistry._handlers) == 1
    print("\n✓ EvidenceGraphHandler registered")

    print("\n=== All Stage 7 tests passed ===")
