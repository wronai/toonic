#!/usr/bin/env python3
"""
Directory Watching — run with: python examples/directory-watching/run.py

Before: ~20 lines manual DirectoryWatcher config.
After:  2 lines with quick API.
"""
from toonic.server.quick import run
from examples._helpers import print_config_summary


if __name__ == "__main__":
    cfg = run("dir:./examples/", goal="monitor directory changes", interval=0, dry_run=True)
    print_config_summary(cfg, title="Directory Monitor")
    print(f"Goal: {cfg.goal[:70]}...")
