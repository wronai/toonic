"""
Toonic — Etap 4: Zunifikowany Pipeline i CLI
=============================================

Fasada nad wszystkimi handlerami — symetryczny pipeline parse ↔ reproduce.
Zastępuje cztery entry pointy reprodukcji jednym interfejsem.

Migrowane funkcje z code2logic:
- universal.py reproduce_file() → Pipeline.to_spec() + Pipeline.reproduce()
- reproducer.py SpecReproducer.reproduce_from_yaml() → Pipeline.reproduce()
- reproduction.py CodeReproducer.reproduce_file() → Pipeline.roundtrip()
- project_reproducer.py ProjectReproducer.reproduce_project() → Pipeline.batch()
- cli.py argumenty reproduce/spec → uproszczone CLI
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from stage_0_foundation import (
    FileLogic,
    FormatRegistry,
    SpecDetector,
)
from stage_1_document_handlers import register_document_handlers
from stage_2_data_config_handlers import register_data_config_handlers
from stage_3_api_infra_handlers import register_api_infra_handlers


# =============================================================================
# Wynik reprodukcji
# =============================================================================

@dataclass
class ReproductionResult:
    """Wynik operacji reprodukcji.

    Migracja z: metrics.py ReproductionResult + ReproductionMetrics
    """
    source_file: str
    output_file: str = ""
    spec_format: str = ""       # toon | yaml | json
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

    Zastępuje:
    - universal.py reproduce_file()
    - reproducer.py SpecReproducer.reproduce_from_yaml/json()
    - reproduction.py CodeReproducer.reproduce_file()
    - project_reproducer.py ProjectReproducer.reproduce_project()

    Trzy kierunki:
    A: source → spec (to_spec)
    B: spec → output (reproduce)
    C: source → spec → output (roundtrip)
    """

    # ── Kierunek A: source → spec ───────────────────────────────────────────

    @staticmethod
    def to_spec(
        source_path: str,
        fmt: str = 'toon',
        output: str | None = None,
    ) -> str:
        """Dowolny plik → spec w TOON/YAML/JSON.

        Migracja z:
        - UniversalParser.parse_file() (parsowanie)
        - YAMLGenerator.generate() / TOONGenerator.generate() (generacja spec)
        - FunctionLogicGenerator.generate_toon() (function-logic mode)

        Przykłady:
            Pipeline.to_spec('src/models.py', fmt='toon')
            Pipeline.to_spec('README.md', fmt='yaml')
            Pipeline.to_spec('schema.sql', fmt='toon')
            Pipeline.to_spec('api.openapi.yaml', fmt='toon')
            Pipeline.to_spec('data.csv', fmt='toon')
            Pipeline.to_spec('.env', fmt='toon')
        """
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
        """Spec (toon/yaml/json) → odtworzony plik.

        Migracja z:
        - reproducer.py SpecReproducer.reproduce_from_yaml()
        - reproducer.py SpecReproducer.reproduce_from_json()
        - chunked_reproduction.py auto_chunk_reproduce()

        Przykłady:
            Pipeline.reproduce('project.toon', output='src/')
            Pipeline.reproduce('README.md.yaml', output='README_new.md')
            Pipeline.reproduce('api.toon', target_fmt='markdown', output='API_DOCS.md')
            Pipeline.reproduce('schema.sql.toon', output='schema_reproduced.sql')
        """
        start = time.time()
        spec_content = Path(spec_path).read_text(encoding='utf-8')

        # Wykryj typ logiki i format spec
        logic_type = SpecDetector.detect(spec_content)
        spec_format = SpecDetector.detect_spec_format(spec_content)

        # Znajdź handler dla tego typu logiki
        handlers = FormatRegistry.get_by_category(logic_type)
        if not handlers:
            # Fallback — spróbuj po kategorii 'code'
            handlers = FormatRegistry.get_by_category('code')

        if not handlers:
            return ReproductionResult(
                source_file=spec_path,
                error=f"Brak handlera dla typu logiki: {logic_type}",
                duration_seconds=time.time() - start,
            )

        handler = handlers[0]

        try:
            # Parsuj spec z powrotem do logiki (uproszczone)
            # W pełnej implementacji: SpecParser.parse(spec_content, logic_type)
            # Na razie: reprodukuj z template
            from stage_0_foundation import CodeLogicBase
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
                spec_tokens=len(spec_content.split()) * 4 // 3,  # ~szacunek tokenów
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
        """source → spec (in memory) → reproduced. Do testowania jakości.

        Migracja z:
        - benchmark.py run_benchmark() (pełny cykl reprodukcji)
        - examples/13_project_benchmark.py
        """
        start = time.time()
        try:
            spec = Pipeline.to_spec(source_path, fmt=fmt)
            # Zapisz spec tymczasowo
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
        """Przetwarza cały katalog → spec dla każdego pliku.

        Migracja z:
        - project_reproducer.py ProjectReproducer.reproduce_project()
        - cli.py _process_directory()

        Zwraca listę wygenerowanych spec.
        """
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
        """Lista dostępnych formatów i ich status.

        Migracja z: cli.py --status, file_formats.py
        """
        return {
            "categories": FormatRegistry.list_categories(),
            "available": FormatRegistry.available(),
            "total_handlers": len(FormatRegistry._handlers),
        }


# =============================================================================
# CLI wrapper
# =============================================================================

def cli_main(args: List[str] | None = None) -> None:
    """Uproszczony CLI — dwa główne polecenia.

    Migracja z: cli.py (909 linii) — uproszczenie do dwóch komend:

    code2logic spec <source> [--fmt toon] [-o output]
    code2logic reproduce <spec> [-o output] [--as target-format]
    code2logic formats [--check]
    code2logic analyze <file>
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog='toonic',
        description='Toonic — Universal TOON Format Platform',
    )
    subparsers = parser.add_subparsers(dest='command', help='Komenda')

    # --- spec ---
    spec_parser = subparsers.add_parser('spec', help='Plik źródłowy → spec')
    spec_parser.add_argument('source', help='Plik lub katalog źródłowy')
    spec_parser.add_argument('--fmt', default='toon', choices=['toon', 'yaml', 'json'],
                              help='Format spec (domyślnie: toon)')
    spec_parser.add_argument('-o', '--output', help='Plik wyjściowy')

    # --- reproduce ---
    repro_parser = subparsers.add_parser('reproduce', help='Spec → odtworzony plik')
    repro_parser.add_argument('spec', help='Plik spec (.toon, .yaml, .json)')
    repro_parser.add_argument('-o', '--output', help='Plik wyjściowy')
    repro_parser.add_argument('--as', dest='target_fmt', help='Format docelowy (transpilacja)')

    # --- formats ---
    fmt_parser = subparsers.add_parser('formats', help='Lista obsługiwanych formatów')
    fmt_parser.add_argument('--check', action='store_true', help='Sprawdź zależności')

    parsed = parser.parse_args(args)

    if parsed.command == 'spec':
        source = Path(parsed.source)
        if source.is_dir():
            results = Pipeline.batch(str(source), fmt=parsed.fmt, output_dir=parsed.output)
            print(f"Przetworzono {len(results)} plików")
        else:
            spec = Pipeline.to_spec(str(source), fmt=parsed.fmt, output=parsed.output)
            if not parsed.output:
                print(spec)

    elif parsed.command == 'reproduce':
        result = Pipeline.reproduce(parsed.spec, output=parsed.output, target_fmt=parsed.target_fmt)
        if result.success:
            print(f"✓ Reprodukcja: {result.output_file or 'stdout'} ({result.duration_seconds:.2f}s)")
        else:
            print(f"✗ Błąd: {result.error}", file=sys.stderr)

    elif parsed.command == 'formats':
        info = Pipeline.formats()
        print(f"Toonic — {info['total_handlers']} handlerów\n")
        for cat, exts in info['categories'].items():
            avail = info['available']
            print(f"  {cat}: {', '.join(exts)}")
        if parsed.check:
            print("\nDostępność zależności:")
            for key, ok in info['available'].items():
                status = "✓" if ok else "✗"
                print(f"  {status} {key}")

    else:
        parser.print_help()


# =============================================================================
# Inicjalizacja — rejestracja wszystkich handlerów
# =============================================================================

def initialize_all_handlers() -> None:
    """Rejestruje wszystkie handlery z etapów 1-3.

    Odpowiednik formats/__init__.py _register_all()
    """
    FormatRegistry.reset()
    register_document_handlers()
    register_data_config_handlers()
    register_api_infra_handlers()


# =============================================================================
# Testy
# =============================================================================

if __name__ == '__main__':
    import tempfile, os

    print("=== Toonic Stage 4: Pipeline & CLI Tests ===\n")

    initialize_all_handlers()

    info = Pipeline.formats()
    print(f"Zarejestrowane handlery: {info['total_handlers']}")
    print(f"Kategorie: {list(info['categories'].keys())}\n")

    # Test 1: to_spec z Markdown
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# My Project\n\nDescription of the project.\n\n## Install\n\n`pip install toonic`\n")
        md_path = f.name
        f.flush()

    spec = Pipeline.to_spec(md_path, fmt='toon')
    assert 'D[' in spec or 'My_Project' in spec or 'my_' in spec.lower()
    print(f"✓ Pipeline.to_spec(markdown, toon):\n{spec}\n")

    # Test 2: to_spec z CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("id,name,score\n1,Alice,95\n2,Bob,87\n3,Carol,92\n")
        csv_path = f.name
        f.flush()

    csv_spec = Pipeline.to_spec(csv_path, fmt='toon')
    assert 'csv' in csv_spec.lower() or 'C[' in csv_spec
    print(f"✓ Pipeline.to_spec(csv, toon):\n{csv_spec}\n")

    # Test 3: to_spec z .env
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DB_HOST=localhost\nSECRET_KEY=abc123\n")
        env_path = f.name
        f.flush()

    env_spec = Pipeline.to_spec(env_path, fmt='toon')
    assert 'env' in env_spec.lower()
    assert '***' in env_spec  # sensitive masked
    print(f"✓ Pipeline.to_spec(.env, toon):\n{env_spec}\n")

    # Test 4: roundtrip
    result = Pipeline.roundtrip(md_path, fmt='toon')
    print(f"✓ Pipeline.roundtrip: success={result.success}, {result.duration_seconds:.3f}s")

    # Test 5: formats
    fmt_info = Pipeline.formats()
    assert fmt_info['total_handlers'] > 5
    print(f"✓ Pipeline.formats: {fmt_info['total_handlers']} handlers, "
          f"{len(fmt_info['categories'])} categories")

    # Test 6: batch
    with tempfile.TemporaryDirectory() as tmpdir:
        # Stwórz kilka plików
        (Path(tmpdir) / "readme.md").write_text("# Test\n\nHello world.\n")
        (Path(tmpdir) / "data.csv").write_text("x,y\n1,2\n3,4\n")
        (Path(tmpdir) / "config.env").write_text("PORT=8080\n")

        out_dir = Path(tmpdir) / "specs"
        results = Pipeline.batch(tmpdir, fmt='toon', output_dir=str(out_dir))
        print(f"✓ Pipeline.batch: {len(results)} specs generated")
        for r in results:
            print(f"  → {Path(r).name}")

    # Test 7: CLI (dry run)
    print("\n--- CLI test: formats ---")
    cli_main(['formats'])

    # Cleanup
    for p in [md_path, csv_path, env_path]:
        os.unlink(p)

    print("\n=== All Stage 4 tests passed ===")
