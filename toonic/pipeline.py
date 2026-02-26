"""
Toonic Pipeline — unified facade for parse ↔ reproduce
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from toonic.core.registry import FormatRegistry
from toonic.core.detector import SpecDetector


# =============================================================================
# Wynik reprodukcji
# =============================================================================

@dataclass
class ReproductionResult:
    """Wynik operacji reprodukcji."""
    source_file: str
    output_file: str = ""
    spec_format: str = ""
    spec_tokens: int = 0
    success: bool = False
    error: str = ""
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Pipeline — główna fasada
# =============================================================================

class Pipeline:
    """Fasada nad całym przepływem parse ↔ reproduce.

    Trzy kierunki:
    A: source → spec (to_spec)
    B: spec → output (reproduce)
    C: source → spec → output (roundtrip)
    """

    _initialized = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Lazy initialization — register handlers on first use."""
        if not cls._initialized:
            from toonic.formats import initialize_all_handlers
            initialize_all_handlers()
            cls._initialized = True

    # ── Kierunek A: source → spec ───────────────────────────────────────────

    @staticmethod
    def to_spec(
        source_path: str,
        fmt: str = 'toon',
        output: str | None = None,
    ) -> str:
        """Dowolny plik → spec w TOON/YAML/JSON.

        Przykłady:
            Pipeline.to_spec('src/models.py', fmt='toon')
            Pipeline.to_spec('README.md', fmt='yaml')
            Pipeline.to_spec('schema.sql', fmt='toon')
        """
        Pipeline._ensure_initialized()

        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Plik nie istnieje: {source_path}")

        handler = FormatRegistry.resolve(path)
        if handler is None:
            raise ValueError(
                f"Brak handlera dla pliku: {source_path} "
                f"(rozszerzenie: {path.suffix}). "
                f"Dostępne formaty: {FormatRegistry.list_categories()}"
            )

        logic = handler.parse(path)
        spec = handler.to_spec(logic, fmt)

        if output:
            Path(output).write_text(spec, encoding='utf-8')

        return spec

    # ── Kierunek B: spec → output ────────────────────────────────────────────

    @staticmethod
    def reproduce(
        spec_path: str,
        output: str | None = None,
        target_fmt: str | None = None,
        client: Any = None,
    ) -> ReproductionResult:
        """Spec (toon/yaml/json) → odtworzony plik."""
        Pipeline._ensure_initialized()

        start = time.time()
        spec_content = Path(spec_path).read_text(encoding='utf-8')

        logic_type = SpecDetector.detect(spec_content)
        spec_format = SpecDetector.detect_spec_format(spec_content)

        handlers = FormatRegistry.get_by_category(logic_type)
        if not handlers:
            handlers = FormatRegistry.get_by_category('code')

        if not handlers:
            return ReproductionResult(
                source_file=spec_path,
                error=f"Brak handlera dla typu logiki: {logic_type}",
                duration_seconds=time.time() - start,
            )

        handler = handlers[0]

        try:
            from toonic.core.models import CodeLogicBase
            dummy_logic = CodeLogicBase(
                source_file=spec_path,
                source_hash="",
                file_category=logic_type,
            )

            result_content = handler.reproduce(dummy_logic, client, target_fmt)

            if output:
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(result_content, encoding='utf-8')

            return ReproductionResult(
                source_file=spec_path,
                output_file=output or "",
                spec_format=spec_format,
                spec_tokens=len(spec_content.split()) * 4 // 3,
                success=True,
                duration_seconds=time.time() - start,
            )

        except Exception as e:
            return ReproductionResult(
                source_file=spec_path,
                error=str(e),
                duration_seconds=time.time() - start,
            )

    # ── Kierunek C: source → spec (in memory) → output ──────────────────────

    @staticmethod
    def roundtrip(
        source_path: str,
        fmt: str = 'toon',
        output: str | None = None,
        client: Any = None,
    ) -> ReproductionResult:
        """source → spec (in memory) → reproduced."""
        Pipeline._ensure_initialized()

        start = time.time()
        try:
            spec = Pipeline.to_spec(source_path, fmt=fmt)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{fmt}', delete=False) as f:
                f.write(spec)
                spec_path = f.name

            result = Pipeline.reproduce(spec_path, output=output, client=client)
            result.duration_seconds = time.time() - start

            import os
            os.unlink(spec_path)

            return result

        except Exception as e:
            return ReproductionResult(
                source_file=source_path,
                error=str(e),
                duration_seconds=time.time() - start,
            )

    # ── Batch processing ─────────────────────────────────────────────────────

    @staticmethod
    def batch(
        source_dir: str,
        fmt: str = 'toon',
        output_dir: str | None = None,
        extensions: List[str] | None = None,
    ) -> List[str]:
        """Przetwarza cały katalog → spec dla każdego pliku."""
        Pipeline._ensure_initialized()

        source = Path(source_dir)
        if not source.is_dir():
            raise NotADirectoryError(f"Nie jest katalogiem: {source_dir}")

        results = []
        for path in sorted(source.rglob('*')):
            if not path.is_file():
                continue
            if path.name.startswith('.'):
                continue
            if extensions and path.suffix not in extensions:
                continue

            handler = FormatRegistry.resolve(path)
            if handler is None:
                continue

            try:
                spec = Pipeline.to_spec(str(path), fmt=fmt)
                if output_dir:
                    out_path = Path(output_dir) / f"{path.stem}{path.suffix}.{fmt}"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(spec, encoding='utf-8')
                    results.append(str(out_path))
                else:
                    results.append(spec)
            except Exception as e:
                print(f"  [WARN] Pominięto {path}: {e}", file=sys.stderr)

        return results

    # ── Informacje ────────────────────────────────────────────────────────────

    @staticmethod
    def formats() -> Dict[str, Any]:
        """Lista dostępnych formatów i ich status."""
        Pipeline._ensure_initialized()

        return {
            "categories": FormatRegistry.list_categories(),
            "available": FormatRegistry.available(),
            "total_handlers": len(FormatRegistry._handlers),
        }
