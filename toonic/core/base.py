"""
BaseHandlerMixin — shared utilities for handlers
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


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
