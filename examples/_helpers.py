#!/usr/bin/env python3
"""
Shared helpers for examples (dry-run output formatting).
"""

from typing import List
from toonic.server.config import ServerConfig


def print_config_summary(cfg: ServerConfig, title: str | None = None) -> None:
    """Print a concise summary of a built ServerConfig."""
    if title:
        print(f"{title}: {len(cfg.sources)} sources, interval={cfg.interval}s")
    else:
        print(f"sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"  [{s.category:10}] {s.path_or_url}")


def print_to_run_hint(preset_or_fn: str, example_args: str = "") -> None:
    """Print a copy-pasteable 'to run' hint."""
    print("\nTo run:")
    print(f"  from toonic.server.quick import {preset_or_fn}")
    args = f'({example_args})' if example_args else ""
    print(f"  {preset_or_fn}{args}.run()")
