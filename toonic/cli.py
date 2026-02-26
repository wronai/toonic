"""
Toonic CLI — command-line interface
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from toonic.pipeline import Pipeline


def cli_main(args: List[str] | None = None) -> None:
    """Uproszczony CLI — dwa główne polecenia.

    toonic spec <source> [--fmt toon] [-o output]
    toonic reproduce <spec> [-o output] [--as target-format]
    toonic formats [--check]
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
            print(f"OK Reprodukcja: {result.output_file or 'stdout'} ({result.duration_seconds:.2f}s)")
        else:
            print(f"ERROR: {result.error}", file=sys.stderr)

    elif parsed.command == 'formats':
        info = Pipeline.formats()
        print(f"Toonic — {info['total_handlers']} handlerów\n")
        for cat, exts in info['categories'].items():
            print(f"  {cat}: {', '.join(exts)}")
        if parsed.check:
            print("\nDostępność zależności:")
            for key, ok in info['available'].items():
                status = "OK" if ok else "MISSING"
                print(f"  [{status}] {key}")

    else:
        parser.print_help()


if __name__ == '__main__':
    cli_main()
