#!/usr/bin/env python3
"""
Data formats — run with: python examples/data-formats/run.py

Before: ~15 lines manual config with multiple file types.
After:  2 lines with quick API.
"""
from toonic.server.quick import run
from examples._helpers import print_config_summary


if __name__ == "__main__":
    cfg = run("./data.csv", "./config.yaml", goal="analyze data formats", interval=0, dry_run=True)
    print_config_summary(cfg, title="Data Formats")
    print(f"Goal: {cfg.goal[:70]}...")
