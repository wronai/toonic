"""
Toonic — Etap 0: Fundament architektoniczny
============================================

Definiuje kluczowe protokoły i rejestr formatów.
Wypełnia istniejące stuby: core/__init__.py, formats/__init__.py

Migrowane funkcje z code2logic:
- BaseParser (base.py) → FileHandler Protocol
- models.py ProjectInfo/ModuleInfo → FileLogic Protocol
- reproducer.py SpecReproducer.reproduce_from_yaml → Pipeline.reproduce
- universal.py reproduce_file → Pipeline.to_spec + Pipeline.reproduce
"""

from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


# =============================================================================
# core/__init__.py — Protocols
# =============================================================================

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


# =============================================================================
# Bazowy mixin z domyślnymi implementacjami
# =============================================================================

class BaseHandlerMixin:
    """Domyślne implementacje wspólne dla wielu handlerów.

    Handlery mogą dziedziczyć z tego mixina zamiast implementować
    wszystko od zera. Nie jest wymagany — Protocol wystarczy.
    """

    def _compute_hash(self, path: Path) -> str:
        """SHA256 pierwszych 8KB pliku — szybki fingerprint."""
        content = path.read_bytes()[:8192]
        return hashlib.sha256(content).hexdigest()[:16]

    def _read_content(self, path: Path, limit: int = 4096) -> str:
        """Czyta początek pliku do content sniffing."""
        return path.read_text(errors='replace')[:limit]

    def _format_toon_header(
        self,
        source_file: str,
        file_type: str,
        **kwargs: Any
    ) -> str:
        """Generuje nagłówek TOON: # filename | type | metryki."""
        parts = [f"# {source_file}", file_type]
        for key, value in kwargs.items():
            parts.append(f"{key}:{value}" if isinstance(value, (int, float)) else str(value))
        return " | ".join(parts)


# =============================================================================
# formats/__init__.py — FormatRegistry
# =============================================================================

class FormatRegistry:
    """Centralny rejestr handlerów z dwuetapowym rozwiązywaniem.

    Rozwiązuje Problem 3 z analizy krytycznej:
    - Explicit registration (nie auto-rejestracja przy imporcie)
    - Jeden ext → wielu kandydatów (nie 1:1)
    - Content sniffing dla disambiguacji

    Migracja z code2logic:
    - SUPPORTED_EXTENSIONS z project_reproducer.py → _ext_index
    - dispatch dict z universal.py → resolve()
    """

    _handlers: List[FileHandler] = []
    _ext_index: Dict[str, List[FileHandler]] = {}

    @classmethod
    def register(cls, handler: FileHandler) -> None:
        """Rejestruje handler. Wywołać z formats/__init__.py."""
        cls._handlers.append(handler)
        for ext in handler.extensions:
            cls._ext_index.setdefault(ext, []).append(handler)

    @classmethod
    def resolve(cls, path: Path, content: str | None = None) -> FileHandler | None:
        """Dwuetapowe wykrywanie: rozszerzenie → content sniffing.

        1. Szukaj kandydatów po rozszerzeniu
        2. Jeśli >1 kandydat — uruchom sniff() na każdym
        3. Zwróć handler z najwyższym score

        Rozwiązuje Problem 2:
        deployment.yaml → [KubernetesHandler, GithubActionsHandler, AnsibleHandler]
        → sniff() → KubernetesHandler (score=0.9)
        """
        ext = path.suffix.lower()
        candidates = cls._ext_index.get(ext, [])

        if len(candidates) == 0:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Wiele kandydatów — content sniffing
        if content is None:
            try:
                content = path.read_text(errors='replace')[:4096]
            except (OSError, UnicodeDecodeError):
                return candidates[0]

        scores = [(h.sniff(path, content), h) for h in candidates]
        best_score, best_handler = max(scores, key=lambda x: x[0])
        return best_handler if best_score > 0.0 else candidates[0]

    @classmethod
    def get_by_category(cls, category: str) -> List[FileHandler]:
        """Zwróć handlery z danej kategorii."""
        return [h for h in cls._handlers if h.category == category]

    @classmethod
    def available(cls) -> Dict[str, bool]:
        """Które handlery mają zainstalowane zależności."""
        return {
            f"{h.category}/{','.join(h.extensions)}": cls._check_deps(h)
            for h in cls._handlers
        }

    @classmethod
    def list_categories(cls) -> Dict[str, List[str]]:
        """Zwróć mapę: kategoria → lista rozszerzeń."""
        categories: Dict[str, List[str]] = {}
        for h in cls._handlers:
            exts = categories.setdefault(h.category, [])
            exts.extend(h.extensions)
        return {k: sorted(set(v)) for k, v in categories.items()}

    @classmethod
    def _check_deps(cls, h: FileHandler) -> bool:
        """Sprawdź czy wymagane pakiety są zainstalowane."""
        return all(
            importlib.util.find_spec(dep) is not None
            for dep in h.requires
        )

    @classmethod
    def reset(cls) -> None:
        """Resetuj rejestr (przydatne w testach)."""
        cls._handlers = []
        cls._ext_index = {}


# =============================================================================
# Bazowe modele logiki
# =============================================================================

@dataclass
class CodeLogicBase:
    """Bazowy model logiki kodu — adaptacja istniejącego ProjectInfo/ModuleInfo.

    Nie zastępuje models.py — rozszerza go o interfejs FileLogic.
    Istniejący ProjectInfo/ModuleInfo/ClassInfo/FunctionInfo pozostają bez zmian.
    """
    source_file: str
    source_hash: str
    file_category: str = "code"
    language: str = "python"
    lines: int = 0
    classes: List[Dict[str, Any]] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "language": self.language,
            "lines": self.lines,
            "classes": self.classes,
            "functions": self.functions,
            "imports": self.imports,
        }

    def complexity(self) -> int:
        return len(self.classes) * 3 + len(self.functions) + self.lines // 100


# =============================================================================
# Spec detector — wykrywanie typu logiki z nagłówka spec
# =============================================================================

class SpecDetector:
    """Wykrywa typ logiki z nagłówka pliku spec (YAML/TOON/JSON).

    Migracja z: reproducer.py SpecReproducer._detect_format()
    """

    @staticmethod
    def detect(content: str) -> str:
        """Wykryj kategorię logiki z nagłówka spec."""
        first_line = content.strip().split('\n')[0].lower()

        if '| python' in first_line or '| javascript' in first_line:
            return 'code'
        if '| markdown' in first_line or '| document' in first_line:
            return 'document'
        if '| postgresql' in first_line or '| mysql' in first_line:
            return 'database'
        if '| kubernetes' in first_line or '| terraform' in first_line:
            return 'infra'
        if '| openapi' in first_line or '| graphql' in first_line:
            return 'api'
        if '| csv' in first_line or '| excel' in first_line:
            return 'data'
        if '| dockerfile' in first_line or '| docker-compose' in first_line:
            return 'config'

        # Heurystyki na podstawie kluczy
        if 'T[' in content[:200] and 'FK→' in content[:500]:
            return 'database'
        if 'M[' in content[:200] and ('f[' in content[:500] or 'c[' in content[:500]):
            return 'code'
        if 'D[' in content[:200] and ('h1:' in content[:500] or 'h2:' in content[:500]):
            return 'document'

        return 'unknown'

    @staticmethod
    def detect_spec_format(content: str) -> str:
        """Wykryj format spec: toon, yaml, json."""
        stripped = content.strip()
        if stripped.startswith('{'):
            return 'json'
        if stripped.startswith('#') and ('M[' in stripped[:200] or 'T[' in stripped[:200]):
            return 'toon'
        return 'yaml'


# =============================================================================
# Testy inline
# =============================================================================

if __name__ == '__main__':
    print("=== Toonic Stage 0: Foundation Tests ===\n")

    # Test 1: FormatRegistry basic
    FormatRegistry.reset()

    class MockHandler:
        extensions = frozenset({'.md', '.markdown'})
        category = 'document'
        requires = ()

        def parse(self, path): return None
        def to_spec(self, logic, fmt): return ""
        def reproduce(self, logic, client, target_fmt): return ""
        def sniff(self, path, content): return 0.5

    handler = MockHandler()
    FormatRegistry.register(handler)

    resolved = FormatRegistry.resolve(Path("README.md"))
    assert resolved is handler, "Registry resolve failed"
    print("✓ FormatRegistry.register + resolve works")

    # Test 2: Available check
    avail = FormatRegistry.available()
    assert "document/{'.md', '.markdown'}" in str(avail) or len(avail) == 1
    print("✓ FormatRegistry.available works")

    # Test 3: Categories
    cats = FormatRegistry.list_categories()
    assert 'document' in cats
    print("✓ FormatRegistry.list_categories works")

    # Test 4: SpecDetector
    assert SpecDetector.detect("# schema.sql | postgresql | 6 tables") == 'database'
    assert SpecDetector.detect("# myproject | 42f | python:35") == 'code'
    assert SpecDetector.detect("# README.md | markdown | 1240w") == 'document'
    print("✓ SpecDetector.detect works")

    assert SpecDetector.detect_spec_format('{"key": "val"}') == 'json'
    assert SpecDetector.detect_spec_format('# proj | M[42]:\n  mod.py') == 'toon'
    assert SpecDetector.detect_spec_format('source_file: test.py') == 'yaml'
    print("✓ SpecDetector.detect_spec_format works")

    # Test 5: CodeLogicBase
    logic = CodeLogicBase(
        source_file="test.py",
        source_hash="abc123",
        lines=100,
        functions=[{"name": "foo", "sig": "() -> None"}],
        classes=[{"name": "Bar"}],
    )
    d = logic.to_dict()
    assert d["source_file"] == "test.py"
    assert logic.complexity() == 3 + 1 + 1  # 1 class*3 + 1 func + 100//100
    print("✓ CodeLogicBase works")

    # Test 6: BaseHandlerMixin
    mixin = BaseHandlerMixin()
    header = mixin._format_toon_header("test.py", "python", lines=100, classes=3)
    assert "# test.py" in header
    assert "lines:100" in header
    print("✓ BaseHandlerMixin works")

    print("\n=== All Stage 0 tests passed ===")
