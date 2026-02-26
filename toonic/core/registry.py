"""
FormatRegistry — central handler registry with two-stage resolution
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

from toonic.core.protocols import FileHandler


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
