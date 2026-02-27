#!/usr/bin/env python3
"""
Code Analysis — run with: python examples/code-analysis/run.py

Before (manual): ~15 lines of ServerConfig + ToonicServer setup.
After (preset):  2 lines.
"""
from toonic.server.quick import code_review
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    # Dry config build (no server start) — safe to run
    builder = code_review("./examples/code-analysis/sample-project/")
    cfg = builder.build_config()
    print_config_summary(cfg, title="Code Review")
    print(f"Goal: {cfg.goal[:60]}...")
    print_to_run_hint("code_review", '"./src/"')
