"""
Document handlers — Markdown, Text, reStructuredText
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from toonic.core.base import BaseHandlerMixin
from toonic.core.registry import FormatRegistry


# =============================================================================
# Model logiki dokumentu
# =============================================================================

@dataclass
class DocumentSection:
    """Pojedyncza sekcja dokumentu."""
    level: int              # 0=brak nagłówka, 1=h1, 2=h2, ...
    title: str              # "Installation", "Quick Start"
    summary: str = ""       # Skrócone streszczenie treści sekcji
    word_count: int = 0
    subsection_count: int = 0
    has_code_blocks: bool = False
    has_links: bool = False
    has_images: bool = False


@dataclass
class DocumentLogic:
    """Logika dokumentu — implementuje FileLogic Protocol."""
    source_file: str
    source_hash: str
    file_category: str = "document"

    title: str = ""
    source_type: str = "markdown"   # markdown | text | rst | asciidoc | pdf | docx
    language: str = "en"
    word_count: int = 0
    sections: List[DocumentSection] = field(default_factory=list)
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "title": self.title,
            "source_type": self.source_type,
            "language": self.language,
            "word_count": self.word_count,
            "sections": [
                {
                    "level": s.level,
                    "title": s.title,
                    "summary": s.summary,
                    "word_count": s.word_count,
                }
                for s in self.sections
            ],
            "frontmatter": self.frontmatter,
        }

    def complexity(self) -> int:
        return len(self.sections) * 2 + self.word_count // 500


# =============================================================================
# Markdown Handler
# =============================================================================

class MarkdownHandler(BaseHandlerMixin):
    """Handler dla plików Markdown (.md, .markdown)."""

    extensions = frozenset({'.md', '.markdown'})
    category = 'document'
    requires = ()

    def parse(self, path: Path) -> DocumentLogic:
        """Parsuje Markdown → DocumentLogic."""
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        # Frontmatter YAML
        frontmatter = {}
        body = content
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    for line in parts[1].strip().split('\n'):
                        if ':' in line:
                            key, _, val = line.partition(':')
                            frontmatter[key.strip()] = val.strip().strip('"\'')
                except Exception:
                    pass
                body = parts[2]

        # Sekcje (nagłówki)
        sections = self._extract_sections(body)

        # Tytuł
        title = frontmatter.get('title', '')
        if not title and sections:
            title = sections[0].title

        total_words = len(body.split())

        return DocumentLogic(
            source_file=path.name,
            source_hash=source_hash,
            title=title,
            source_type='markdown',
            language=frontmatter.get('lang', frontmatter.get('language', 'en')),
            word_count=total_words,
            sections=sections,
            frontmatter=frontmatter,
        )

    def _extract_sections(self, content: str) -> List[DocumentSection]:
        """Ekstrakcja sekcji z treści Markdown."""
        sections: List[DocumentSection] = []
        current_lines: List[str] = []
        current_level = 0
        current_title = ""

        for line in content.split('\n'):
            header_match = re.match(r'^(#{1,6})\s+(.+)', line)
            if header_match:
                # Zapisz poprzednią sekcję
                if current_title or current_lines:
                    section_text = '\n'.join(current_lines)
                    sections.append(DocumentSection(
                        level=current_level,
                        title=current_title,
                        summary=self._summarize(section_text),
                        word_count=len(section_text.split()),
                        has_code_blocks='```' in section_text,
                        has_links='](http' in section_text or ']: http' in section_text,
                        has_images='![' in section_text,
                    ))
                current_level = len(header_match.group(1))
                current_title = header_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Ostatnia sekcja
        if current_title or current_lines:
            section_text = '\n'.join(current_lines)
            sections.append(DocumentSection(
                level=current_level,
                title=current_title,
                summary=self._summarize(section_text),
                word_count=len(section_text.split()),
                has_code_blocks='```' in section_text,
                has_links='](http' in section_text,
                has_images='![' in section_text,
            ))

        return sections

    def _summarize(self, text: str, max_words: int = 15) -> str:
        """Skrócone streszczenie: pierwsze zdanie lub N słów."""
        text = text.strip()
        if not text:
            return ""
        sentences = re.split(r'[.!?]\s', text)
        if sentences:
            first = sentences[0].strip()
            words = first.split()
            if len(words) <= max_words:
                return first
            return ' '.join(words[:max_words]) + '...'
        return ' '.join(text.split()[:max_words]) + '...'

    def to_spec(self, logic: DocumentLogic, fmt: str = 'toon') -> str:
        """Generuje spec dokumentu w formacie TOON, YAML lub JSON."""
        if fmt == 'toon':
            return self._to_toon(logic)
        elif fmt == 'yaml':
            return self._to_yaml(logic)
        elif fmt == 'json':
            return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)
        raise ValueError(f"Nieznany format: {fmt}")

    def _to_toon(self, doc: DocumentLogic) -> str:
        lines = [
            self._format_toon_header(
                doc.source_file, doc.source_type,
                **{f"{doc.word_count}w": ""}
            )
        ]
        if doc.sections:
            lines.append(f"D[{len(doc.sections)}]:")
            for s in doc.sections:
                title_clean = s.title.replace(' ', '_')[:30]
                level_prefix = f"h{s.level}" if s.level > 0 else "p"
                summary_short = s.summary[:50].replace('\n', ' ')
                parts = [f"  {level_prefix}:{title_clean}"]
                if summary_short:
                    parts.append(summary_short)
                if s.word_count:
                    parts.append(f"{s.word_count}w")
                lines.append(" | ".join(parts))
        return '\n'.join(lines)

    def _to_yaml(self, doc: DocumentLogic) -> str:
        lines = [
            f"# doc: {doc.source_file} | {doc.source_type} | {doc.word_count} words",
            f'title: "{doc.title}"',
            f"lang: {doc.language}",
        ]
        if doc.sections:
            lines.append("sections:")
            for s in doc.sections:
                level_name = f"h{s.level}" if s.level > 0 else "paragraph"
                lines.append(f'  - {level_name}: "{s.title}"')
                if s.summary:
                    lines.append(f'    summary: "{s.summary}"')
                if s.word_count:
                    lines.append(f"    words: {s.word_count}")
        return '\n'.join(lines)

    def reproduce(self, logic: DocumentLogic, client: Any = None, target_fmt: str | None = None) -> str:
        """Odtwarza dokument z logiki."""
        if client is None:
            return self._reproduce_template(logic)
        chunks = self._chunk_by_sections(logic)
        pieces = []
        for chunk in chunks:
            prompt = self._get_chunk_prompt(chunk, logic)
            response = client.generate(prompt)
            pieces.append(response)
        return '\n\n'.join(pieces)

    def _reproduce_template(self, doc: DocumentLogic) -> str:
        lines = []
        if doc.title:
            lines.append(f"# {doc.title}\n")
        for s in doc.sections:
            prefix = '#' * max(s.level, 1)
            lines.append(f"{prefix} {s.title}\n")
            if s.summary:
                lines.append(f"{s.summary}\n")
            else:
                lines.append(f"<!-- TODO: {s.word_count} words -->\n")
        return '\n'.join(lines)

    def _chunk_by_sections(self, doc: DocumentLogic) -> List[DocumentSection]:
        return [s for s in doc.sections if s.level <= 2]

    def _get_chunk_prompt(self, section: DocumentSection, doc: DocumentLogic) -> str:
        return (
            f"Odtwórz sekcję dokumentu '{doc.title}'.\n"
            f"Sekcja: {section.title}\n"
            f"Streszczenie: {section.summary}\n"
            f"Docelowa liczba słów: ~{section.word_count}\n"
            f"Format: {doc.source_type}\n"
            f"Styl: techniczny, zwięzły\n\n"
            f"Wygeneruj TYLKO treść sekcji (bez nagłówka)."
        )

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if re.search(r'^#{1,6}\s+', content, re.MULTILINE):
            score += 0.5
        if content.startswith('---') and '\n---' in content[3:]:
            score += 0.3
        if '```' in content:
            score += 0.1
        if '](http' in content or '![' in content:
            score += 0.1
        return min(score, 1.0)


# =============================================================================
# Text Handler
# =============================================================================

class TextHandler(BaseHandlerMixin):
    """Handler dla plików tekstowych (.txt)."""

    extensions = frozenset({'.txt'})
    category = 'document'
    requires = ()

    def parse(self, path: Path) -> DocumentLogic:
        content = path.read_text(errors='replace')
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

        sections = []
        for i, para in enumerate(paragraphs):
            sections.append(DocumentSection(
                level=0,
                title=f"paragraph_{i+1}",
                summary=para[:80] + ('...' if len(para) > 80 else ''),
                word_count=len(para.split()),
            ))

        return DocumentLogic(
            source_file=path.name,
            source_hash=self._compute_hash(path),
            title=path.stem,
            source_type='text',
            word_count=len(content.split()),
            sections=sections,
        )

    def to_spec(self, logic: DocumentLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | text | {logic.word_count}w"]
            lines.append(f"P[{len(logic.sections)}]:")
            for s in logic.sections:
                lines.append(f"  {s.summary[:60]} | {s.word_count}w")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: DocumentLogic, client: Any = None, target_fmt: str | None = None) -> str:
        return '\n\n'.join(s.summary for s in logic.sections)

    def sniff(self, path: Path, content: str) -> float:
        return 0.1  # niski — txt to fallback


# =============================================================================
# RST Handler
# =============================================================================

class RstHandler(BaseHandlerMixin):
    """Handler dla reStructuredText (.rst)."""

    extensions = frozenset({'.rst'})
    category = 'document'
    requires = ()

    def parse(self, path: Path) -> DocumentLogic:
        content = path.read_text(errors='replace')

        sections = []
        lines_list = content.split('\n')
        for i, line in enumerate(lines_list):
            if i > 0 and line and all(c in '=-~^"' for c in line.strip()) and len(line.strip()) >= 3:
                title = lines_list[i-1].strip()
                if title:
                    level = {'=': 1, '-': 2, '~': 3, '^': 4}.get(line.strip()[0], 3)
                    sections.append(DocumentSection(
                        level=level,
                        title=title,
                        word_count=0,
                    ))

        return DocumentLogic(
            source_file=path.name,
            source_hash=self._compute_hash(path),
            title=sections[0].title if sections else path.stem,
            source_type='rst',
            word_count=len(content.split()),
            sections=sections,
        )

    def to_spec(self, logic: DocumentLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | rst | {logic.word_count}w"]
            lines.append(f"D[{len(logic.sections)}]:")
            for s in logic.sections:
                lines.append(f"  h{s.level}:{s.title[:40]}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: DocumentLogic, client: Any = None, target_fmt: str | None = None) -> str:
        lines = []
        underlines = {1: '=', 2: '-', 3: '~', 4: '^'}
        for s in logic.sections:
            lines.append(s.title)
            char = underlines.get(s.level, '-')
            lines.append(char * len(s.title))
            lines.append('')
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if re.search(r'^[=\-~^]{3,}\s*$', content, re.MULTILINE):
            score += 0.4
        if '.. ' in content:
            score += 0.3
        if ':ref:' in content or ':doc:' in content:
            score += 0.2
        return min(score, 1.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_document_handlers() -> None:
    """Rejestruje handlery dokumentów w FormatRegistry."""
    for handler in [MarkdownHandler(), TextHandler(), RstHandler()]:
        FormatRegistry.register(handler)
