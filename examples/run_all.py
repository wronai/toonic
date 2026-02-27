#!/usr/bin/env python3
"""
Run and verify all Toonic examples.

Usage:
    python examples/run_all.py              # verify all (dry-run, no server)
    python examples/run_all.py --list       # list available examples
    python examples/run_all.py --show demo   # show example details
    python examples/run_all.py --run demo    # run a specific demo
    python examples/run_all.py --preset security-audit ./src/  # run preset
    python examples/run_all.py --execute     # execute local-safe example scripts sequentially
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

EXAMPLES_DIR = Path(__file__).parent


# ── Helper functions ─────────────────────────────────────────

def _repo_root() -> Path:
    return EXAMPLES_DIR.parent


def _run_py(script: Path, *, timeout_s: int = 30) -> subprocess.CompletedProcess:
    env = dict(**{k: v for k, v in (getattr(__import__('os'), 'environ')).items()})
    # Make examples runnable without editable install
    env["PYTHONPATH"] = f"{_repo_root()}:{env.get('PYTHONPATH','')}".rstrip(":")
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=timeout_s,
        env=env,
        cwd=str(_repo_root()),
    )


# ── Example registry ─────────────────────────────────────────

EXAMPLES: Dict[str, Dict[str, Any]] = {
    "code-analysis": {
        "desc": "Analyze Python code for bugs, security issues, quality",
        "quick": 'from toonic.server.quick import code_review\ncode_review("./examples/code-analysis/sample-project/")',
        "preset": "code-review",
        "sources": ["./examples/code-analysis/sample-project/"],
        "has_demo": False,
    },
    "security-audit": {
        "desc": "Security audit: secrets, injections, OWASP Top 10",
        "quick": 'from toonic.server.quick import security_audit\nsecurity_audit("./examples/code-analysis/sample-project/")',
        "preset": "security-audit",
        "sources": ["./examples/code-analysis/sample-project/"],
        "has_demo": False,
    },
    "log-monitoring": {
        "desc": "Real-time log monitoring with priority and triggers",
        "quick": 'from toonic.server.quick import log_monitor\nlog_monitor("log:./docker/test-data/sample.logfile")',
        "preset": "log-monitor",
        "sources": ["log:./docker/test-data/sample.logfile"],
        "has_demo": True,
        "demo_script": "generate_logs.py",
    },
    "video-monitoring": {
        "desc": "CCTV monitoring with YOLO detection and event analysis",
        "quick": 'from toonic.server.quick import cctv_monitor\ncctv_monitor("rtsp://cam:554/stream")',
        "preset": "cctv-monitor",
        "sources": ["rtsp://localhost:8554/test-cam1"],
        "has_demo": False,
    },
    "video-captioning": {
        "desc": "Video stream captioning with multimodal LLM",
        "quick": 'from toonic.server.quick import run\nrun("rtsp://cam:554/stream", goal="caption each scene change")',
        "preset": None,
        "sources": ["rtsp://localhost:8554/test-cam1"],
        "has_demo": False,
    },
    "http-monitoring": {
        "desc": "HTTP/API endpoint monitoring: uptime, SSL, headers",
        "quick": 'from toonic.server.quick import web_monitor\nweb_monitor("https://api.example.com/health")',
        "preset": "web-monitor",
        "sources": ["https://httpbin.org/get"],
        "has_demo": False,
    },
    "infra-monitoring": {
        "desc": "Docker + Database + Network + Process monitoring",
        "quick": 'from toonic.server.quick import infra_health\ninfra_health("docker:*", "db:./app.db", "net:8.8.8.8")',
        "preset": "infra-health",
        "sources": ["docker:*"],
        "has_demo": False,
    },
    "directory-watching": {
        "desc": "Directory structure monitoring: new/deleted/modified files",
        "quick": 'from toonic.server.quick import run\nrun("dir:./examples/", goal="monitor directory changes")',
        "preset": None,
        "sources": ["dir:./examples/"],
        "has_demo": False,
    },
    "multi-source": {
        "desc": "Combined code + logs + video + infra monitoring",
        "quick": 'from toonic.server.quick import full_stack\nfull_stack("./src/", "log:./app.log", "docker:*")',
        "preset": "full-stack",
        "sources": ["./examples/code-analysis/sample-project/", "log:./docker/test-data/sample.logfile"],
        "has_demo": False,
    },
    "data-formats": {
        "desc": "Multi-format data monitoring: CSV, JSON, YAML, etc.",
        "quick": 'from toonic.server.quick import run\nrun("./data.csv", "./config.yaml", goal="analyze data formats")',
        "preset": None,
        "sources": [],
        "has_demo": False,
    },
    "archive-monitoring": {
        "desc": "Analyze archives (zip/tar) by unpacking and watching extracted contents",
        "quick": 'from toonic.server.quick import watch_archive\nwatch_archive("./bundle.zip", include_files_as_sources=True)',
        "preset": None,
        "sources": [],
        "has_demo": False,
    },
    "protocol-recipes": {
        "desc": "Protocol source recipes: http/rtsp/db/net/proc/docker/dir combinations",
        "quick": 'from toonic.server.quick import watch\nwatch("https://httpbin.org/get", "net:8.8.8.8", "proc:nginx")',
        "preset": None,
        "sources": [
            "https://httpbin.org/get",
            "rtsp://localhost:8554/test-cam1",
            "postgresql://user:pass@db:5432/app",
            "docker:*",
            "net:8.8.8.8",
            "proc:nginx",
            "dir:./examples/",
        ],
        "has_demo": True,
        "demo_script": "run.py",
    },
    "programmatic-api": {
        "desc": "Low-level Python API: accumulator, pipeline, parser",
        "quick": "python examples/programmatic-api/demo_quick.py",
        "preset": None,
        "sources": [],
        "has_demo": True,
        "demo_scripts": ["demo_quick.py", "demo_accumulator.py", "demo_pipeline.py"],
    },
}


# ── Verification (import + build_config only, no server start) ──

def verify_imports() -> List[str]:
    """Verify all toonic modules import correctly."""
    errors = []
    modules = [
        "toonic.server.quick",
        "toonic.server.config",
        "toonic.server.main",
        "toonic.server.models",
        "toonic.server.core.accumulator",
        "toonic.server.llm.pipeline",
        "toonic.server.llm.caller",
        "toonic.server.llm.parser",
        "toonic.server.llm.prompts",
        "toonic.server.triggers.dsl",
        "toonic.server.watchers.base",
        "toonic.pipeline",
        "toonic.cli",
    ]
    for mod_name in modules:
        try:
            importlib.import_module(mod_name)
        except Exception as e:
            errors.append(f"  FAIL: {mod_name} — {e}")
    return errors


def verify_presets() -> List[str]:
    """Verify all presets build without error."""
    errors = []
    from toonic.server.quick import PRESETS
    for name, info in PRESETS.items():
        try:
            builder = info["fn"]("./examples/code-analysis/sample-project/")
            cfg = builder.build_config()
            assert cfg.goal, f"Preset {name} has empty goal"
            assert cfg.sources, f"Preset {name} has no sources"
        except Exception as e:
            errors.append(f"  FAIL: preset '{name}' — {e}")
    return errors


def verify_config_builds() -> List[str]:
    """Verify each example can build a ServerConfig."""
    errors = []
    from toonic.server.quick import watch
    for name, ex in EXAMPLES.items():
        if not ex["sources"]:
            continue
        try:
            builder = watch(*ex["sources"])
            builder.goal(ex["desc"])
            builder.interval(0)
            cfg = builder.build_config()
            assert len(cfg.sources) > 0
        except Exception as e:
            errors.append(f"  FAIL: example '{name}' — {e}")
    return errors


def verify_demos() -> List[str]:
    """Run demo scripts that don't require network/server."""
    errors = []
    demo_dir = EXAMPLES_DIR / "programmatic-api"
    for script in ["demo_quick.py", "demo_accumulator.py", "demo_pipeline.py"]:
        path = demo_dir / script
        if not path.exists():
            errors.append(f"  MISSING: {path}")
            continue
        result = _run_py(path, timeout_s=30)
        if result.returncode != 0:
            errors.append(f"  FAIL: {script} — {(result.stderr or result.stdout)[:200]}")
    return errors


def verify_all() -> bool:
    """Run all verifications."""
    print("=" * 60)
    print("  Toonic Examples — Verification Suite")
    print("=" * 60)

    all_ok = True

    print("\n1. Imports...")
    errs = verify_imports()
    if errs:
        all_ok = False
        for e in errs:
            print(e)
    else:
        print("  OK — all modules import successfully")

    print("\n2. Presets...")
    errs = verify_presets()
    if errs:
        all_ok = False
        for e in errs:
            print(e)
    else:
        print("  OK — all presets build correctly")

    print("\n3. Example configs...")
    errs = verify_config_builds()
    if errs:
        all_ok = False
        for e in errs:
            print(e)
    else:
        print("  OK — all examples build ServerConfig")

    print("\n4. Demo scripts...")
    errs = verify_demos()
    if errs:
        all_ok = False
        for e in errs:
            print(e)
    else:
        print("  OK — all demo scripts run successfully")

    print("\n" + "=" * 60)
    if all_ok:
        print("  ALL VERIFICATIONS PASSED")
    else:
        print("  SOME VERIFICATIONS FAILED")
    print("=" * 60)
    return all_ok


# ── Execute examples (sequential) ─────────────────────────────

def execute_all(*, continue_on_error: bool = True) -> bool:
    """Execute local-safe example scripts sequentially.

    Notes:
        - We only run scripts that are designed to be safe (dry build / no server).
        - Examples that require external services are skipped with a reason.
    """
    scripts: List[Dict[str, Any]] = []

    # Standard run.py entrypoints
    for run_py in sorted(EXAMPLES_DIR.glob("*/run.py")):
        example_name = run_py.parent.name
        scripts.append({
            "name": f"{example_name}/run.py",
            "path": run_py,
            "timeout": 30,
        })

    # Security audit quick demo (dry build)
    quick_audit = EXAMPLES_DIR / "security-audit" / "quick_audit.py"
    if quick_audit.exists():
        scripts.append({"name": "security-audit/quick_audit.py", "path": quick_audit, "timeout": 30})

    # Programmatic API demos (should run offline)
    demo_dir = EXAMPLES_DIR / "programmatic-api"
    for script in ["demo_quick.py", "demo_accumulator.py", "demo_pipeline.py"]:
        p = demo_dir / script
        if p.exists():
            scripts.append({"name": f"programmatic-api/{script}", "path": p, "timeout": 30})

    skipped = {
        # Requires RTSP stream to actually do something meaningful (we keep run.py dry), but might still import OpenCV.
        "video-captioning": "RTSP stream + optional OpenCV/ultralytics dependencies",
        # Infra examples may depend on Docker daemon; our run.py is dry, but keep a skip option if needed later.
    }

    print("=" * 60)
    print("  Toonic Examples — Execute (sequential)")
    print("=" * 60)

    ok = True
    for item in scripts:
        name = item["name"]
        path: Path = item["path"]
        ex_dir = path.parent
        ex_name = ex_dir.name
        if ex_name in skipped:
            print(f"\nSKIP: {name} — {skipped[ex_name]}")
            continue
        print(f"\nRUN: {name}")
        try:
            result = _run_py(path, timeout_s=int(item.get("timeout", 30)))
        except subprocess.TimeoutExpired:
            ok = False
            print(f"  FAIL (timeout): {name}")
            if not continue_on_error:
                break
            continue

        if result.returncode != 0:
            ok = False
            out = (result.stdout or "")
            err = (result.stderr or "")
            tail = (err or out).splitlines()[-25:]
            print(f"  FAIL (exit={result.returncode}): {name}")
            if tail:
                print("  --- output tail ---")
                for line in tail:
                    print(f"  {line}")
            if not continue_on_error:
                break
        else:
            print(f"  OK: {name}")

    print("\n" + "=" * 60)
    print("  EXECUTION OK" if ok else "  EXECUTION HAD FAILURES")
    print("=" * 60)
    return ok


# ── List / Show ──────────────────────────────────────────────

def list_examples():
    """List all available examples."""
    print("=" * 60)
    print("  Toonic Examples")
    print("=" * 60)

    print("\n  Presets (1-liner monitoring):\n")
    from toonic.server.quick import PRESETS
    for name, info in PRESETS.items():
        print(f"    {name:20s}  {info['desc']}")

    print("\n  Examples (full demos):\n")
    for name, ex in EXAMPLES.items():
        marker = " [has scripts]" if ex.get("has_demo") else ""
        print(f"    {name:20s}  {ex['desc']}{marker}")

    print(f"\n  Total: {len(PRESETS)} presets, {len(EXAMPLES)} examples")
    print("\n  Quick usage:")
    print("    from toonic.server.quick import security_audit")
    print('    security_audit("./src/").run()')
    print()


def show_example(name: str):
    """Show details and quick-start code for an example."""
    if name not in EXAMPLES:
        print(f"Unknown example: {name}")
        print(f"Available: {', '.join(EXAMPLES.keys())}")
        return

    ex = EXAMPLES[name]
    print(f"\n  Example: {name}")
    print(f"  {ex['desc']}")
    print(f"\n  Quick start:")
    for line in ex["quick"].split("\n"):
        print(f"    {line}")

    readme = EXAMPLES_DIR / name / "README.md"
    if readme.exists():
        print(f"\n  README: {readme}")

    if ex.get("preset"):
        print(f"\n  Preset: toonic.server.quick.{ex['preset'].replace('-', '_')}")


# ── Main ─────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Toonic examples runner")
    parser.add_argument("--list", action="store_true", help="List examples")
    parser.add_argument("--show", type=str, help="Show example details")
    parser.add_argument("--verify", action="store_true", help="Verify all examples")
    parser.add_argument("--execute", action="store_true", help="Execute local-safe example scripts sequentially")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first execution failure (with --execute)")
    parser.add_argument("--run", type=str, help="Run a demo script")
    parser.add_argument("--preset", type=str, help="Run a preset (dry config build)")
    parser.add_argument("sources", nargs="*", help="Sources for preset")
    args = parser.parse_args()

    if args.list:
        list_examples()
    elif args.show:
        show_example(args.show)
    elif args.execute:
        ok = execute_all(continue_on_error=not args.fail_fast)
        sys.exit(0 if ok else 1)
    elif args.run:
        demo_dir = EXAMPLES_DIR / "programmatic-api"
        script = demo_dir / args.run
        if not script.exists():
            script = demo_dir / f"demo_{args.run}.py"
        if script.exists():
            subprocess.run([sys.executable, str(script)])
        else:
            print(f"Script not found: {args.run}")
    elif args.preset:
        from toonic.server.quick import PRESETS
        if args.preset in PRESETS:
            sources = args.sources or ["./examples/code-analysis/sample-project/"]
            builder = PRESETS[args.preset]["fn"](*sources)
            cfg = builder.build_config()
            print(f"Preset: {args.preset}")
            print(f"Goal:   {cfg.goal}")
            print(f"Sources: {len(cfg.sources)}")
            for s in cfg.sources:
                print(f"  [{s.category}] {s.path_or_url}")
        else:
            print(f"Unknown preset: {args.preset}")
            print(f"Available: {', '.join(PRESETS.keys())}")
    else:
        ok = verify_all()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
