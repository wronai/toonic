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
    toonic init "description" [--name NAME] [--lang python]
    toonic autopilot [DIR] [--goal GOAL] [--max-iter N]
    toonic examples [--list] [--verify] [--preset NAME] [SOURCES...]
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

    # --- init ---
    init_parser = subparsers.add_parser('init', help='Scaffold new project from description')
    init_parser.add_argument('description', help='Project description (natural language)')
    init_parser.add_argument('--name', default='', help='Project name')
    init_parser.add_argument('--lang', default='', help='Language (python, javascript)')
    init_parser.add_argument('-o', '--output', default='', help='Output directory')

    # --- examples ---
    ex_parser = subparsers.add_parser('examples', help='List, verify, run examples & presets')
    ex_parser.add_argument('--list', '-l', action='store_true', help='List examples & presets')
    ex_parser.add_argument('--verify', action='store_true', help='Verify all examples')
    ex_parser.add_argument('--show', type=str, help='Show example details')
    ex_parser.add_argument('--preset', '-p', type=str, help='Build config from preset (dry)')
    ex_parser.add_argument('--run-demo', type=str, help='Run a demo script')
    ex_parser.add_argument('sources', nargs='*', help='Sources for preset')

    # --- autopilot ---
    auto_parser = subparsers.add_parser('autopilot', help='Autonomous development loop')
    auto_parser.add_argument('project_dir', nargs='?', default='.', help='Project directory')
    auto_parser.add_argument('--goal', '-g', default='build MVP', help='Development goal')
    auto_parser.add_argument('--max-iter', type=int, default=20, help='Max iterations')
    auto_parser.add_argument('--interval', type=float, default=10.0, help='Seconds between iterations')
    auto_parser.add_argument('--model', '-m', default='', help='LLM model override')
    auto_parser.add_argument('--dry-run', action='store_true', help='Show changes without writing')
    auto_parser.add_argument('--no-test', action='store_true', help='Skip auto-testing')

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

    elif parsed.command == 'init':
        from toonic.autopilot.scaffold import ProjectScaffold
        spec, files = ProjectScaffold.init(
            description=parsed.description,
            name=parsed.name,
            language=parsed.lang,
            output_dir=parsed.output,
        )
        print(f"\n  Project '{spec.name}' created!")
        print(f"  ─────────────────────────────────")
        print(f"  Type:     {spec.project_type}")
        print(f"  Language: {spec.language}")
        print(f"  Files:    {len(files)}")
        print(f"  Dir:      {parsed.output or './' + spec.name}/")
        print(f"\n  Next steps:")
        print(f"    cd {spec.name}")
        print(f"    toonic autopilot . --goal 'build MVP'")
        print()

    elif parsed.command == 'examples':
        from examples.run_all import (
            list_examples, show_example, verify_all, EXAMPLES,
        )
        if parsed.list:
            list_examples()
        elif parsed.verify:
            ok = verify_all()
            if not ok:
                sys.exit(1)
        elif parsed.show:
            show_example(parsed.show)
        elif parsed.preset:
            from toonic.server.quick import PRESETS
            name = parsed.preset
            if name in PRESETS:
                sources = parsed.sources or ['./examples/code-analysis/sample-project/']
                builder = PRESETS[name]['fn'](*sources)
                cfg = builder.build_config()
                print(f"  Preset:  {name}")
                print(f"  Goal:    {cfg.goal}")
                print(f"  Sources: {len(cfg.sources)}")
                for s in cfg.sources:
                    print(f"    [{s.category}] {s.path_or_url}")
                print(f"\n  To run: from toonic.server.quick import {name.replace('-', '_')}")
                print(f'  {name.replace("-", "_")}({", ".join(repr(s) for s in sources)}).run()')
            else:
                print(f"Unknown preset: {name}")
                print(f"Available: {', '.join(PRESETS.keys())}")
                sys.exit(1)
        elif parsed.run_demo:
            import subprocess
            from pathlib import Path as P
            script = P('examples/programmatic-api') / parsed.run_demo
            if not script.exists():
                script = P('examples/programmatic-api') / f'demo_{parsed.run_demo}.py'
            if script.exists():
                subprocess.run([sys.executable, str(script)])
            else:
                print(f"Script not found: {parsed.run_demo}")
                sys.exit(1)
        else:
            list_examples()

    elif parsed.command == 'autopilot':
        import asyncio
        from toonic.autopilot.loop import AutopilotLoop, AutopilotConfig
        config = AutopilotConfig(
            project_dir=parsed.project_dir,
            goal=parsed.goal,
            max_iterations=parsed.max_iter,
            interval_s=parsed.interval,
            model=parsed.model,
            dry_run=parsed.dry_run,
            auto_test=not parsed.no_test,
        )
        loop = AutopilotLoop(config)

        async def _event_printer(event_type, data):
            if event_type == 'iteration_start':
                print(f"\n── Iteration {data['iteration']} ──")
            elif event_type == 'llm_response':
                print(f"  LLM: {data.get('description', '')[:80]}")
                print(f"  Files: {data.get('files_count', 0)}")
            elif event_type == 'iteration_done':
                written = data.get('files_written', [])
                if written:
                    for f in written:
                        print(f"  ✓ {f}")
                if data.get('error'):
                    print(f"  ✗ {data['error'][:100]}")
            elif event_type == 'complete':
                print(f"\n  ✓ ROADMAP complete in {data['iterations']} iterations!")
            elif event_type == 'error':
                print(f"  ERROR: {data.get('error', data.get('message', ''))}")

        try:
            results = asyncio.run(loop.run(on_event=_event_printer))
            print(f"\nAutopilot finished: {len(results)} actions")
        except KeyboardInterrupt:
            print("\nAutopilot stopped.")

    else:
        parser.print_help()


if __name__ == '__main__':
    cli_main()
