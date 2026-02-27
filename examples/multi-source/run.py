#!/usr/bin/env python3
"""
Multi-Source Monitoring — run with: python examples/multi-source/run.py

Before: ~30 lines of manual config + trigger YAML + token allocation.
After:  4 lines with preset.
"""
from toonic.server.quick import full_stack
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = full_stack(
        "./examples/code-analysis/sample-project/",
        "log:./docker/test-data/sample.logfile",
        "docker:*",
    )
    cfg = builder.build_config()
    print_config_summary(cfg, title="Full-Stack")
    print(f"Goal: {cfg.goal[:70]}...")
    print_to_run_hint("full_stack", '"./src/", "log:./app.log", "docker:*"')
