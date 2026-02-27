#!/usr/bin/env python3
"""
Multi-Source Monitoring — run with: python examples/multi-source/run.py

Before: ~30 lines of manual config + trigger YAML + token allocation.
After:  4 lines with preset.
"""
from toonic.server.quick import full_stack

if __name__ == "__main__":
    builder = full_stack(
        "./examples/code-analysis/sample-project/",
        "log:./docker/test-data/sample.logfile",
        "docker:*",
    )
    cfg = builder.build_config()
    print(f"Full-Stack: {len(cfg.sources)} sources, interval={cfg.interval}s")
    print(f"Goal: {cfg.goal[:70]}...")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run:")
    print('  from toonic.server.quick import full_stack')
    print('  full_stack("./src/", "log:./app.log", "docker:*").run()')
