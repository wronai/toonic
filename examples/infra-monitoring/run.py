#!/usr/bin/env python3
"""
Infrastructure Monitoring — run with: python examples/infra-monitoring/run.py

Before: ~25 lines of manual config + trigger YAML loading.
After:  3 lines with preset.
"""
from toonic.server.quick import infra_health
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = infra_health("docker:*", "net:8.8.8.8,1.1.1.1")
    cfg = builder.build_config()
    print_config_summary(cfg, title="Infra Health")
    print(f"Goal: {cfg.goal[:70]}...")
    print_to_run_hint("infra_health", '"docker:*", "db:./app.db", "net:8.8.8.8"')
