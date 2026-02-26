"""
Core Protocols — FileLogic and FileHandler
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FileLogic(Protocol):
    """Dane logiczne pliku — minimalny interfejs.

    Zastępuje potrzebę osobnego BaseLogic dataclass.
    Każdy model logiki (CodeLogic, DocumentLogic, SqlSchemaLogic...)
    implementuje ten protokół.
    """
    source_file: str
    source_hash: str
    file_category: str  # "code" | "document" | "data" | "config" | "api" | "infra" | ...

    def to_dict(self) -> dict:
        """Serializacja do dict (dla generatorów YAML/TOON/JSON)."""
        ...

    def complexity(self) -> int:
        """Szacunkowa złożoność pliku (wpływa na chunking reprodukcji)."""
        ...


class FileHandler(Protocol):
    """Jeden handler = jeden typ pliku. Trzy metody, nie trzy klasy.

    Zastępuje wzorzec: Parser + Generator + Reproducer + Logic (4 klasy per format).
    Migracja z code2logic:
    - parse() ← UniversalParser.parse_file() / DocumentParser.parse()
    - to_spec() ← YAMLGenerator.generate() / TOONGenerator.generate()
    - reproduce() ← SpecReproducer.reproduce_from_yaml() / CodeReproducer.reproduce_file()
    """

    # Które pliki obsługuje?
    extensions: frozenset[str]      # np. {'.md', '.markdown'}
    category: str                   # np. 'document'
    requires: tuple[str, ...]       # np. ('python-docx',) lub ()

    def parse(self, path: Path) -> FileLogic:
        """Kierunek A: plik źródłowy → logika."""
        ...

    def to_spec(self, logic: FileLogic, fmt: str) -> str:
        """Kierunek B: logika → spec string (yaml/toon/json)."""
        ...

    def reproduce(self, logic: FileLogic, client: Any, target_fmt: str | None) -> str:
        """Kierunek C: logika → odtworzony plik (z LLM)."""
        ...

    def sniff(self, path: Path, content: str) -> float:
        """Pewność 0.0–1.0 że ten plik to nasz typ (content sniffing).

        Rozwiązuje Problem 2 z analizy krytycznej:
        .yaml może być OpenAPI, Kubernetes, GitHub Actions, Ansible...
        sniff() sprawdza treść, nie tylko rozszerzenie.
        """
        return 0.0  # domyślnie: rozszerzenie wystarczy
