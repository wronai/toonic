#!/usr/bin/env python3
"""
Log Monitoring — run with: python examples/log-monitoring/run.py

Before: ~20 lines of manual ServerConfig + trigger setup.
After:  2 lines with preset.
"""
from toonic.server.quick import log_monitor
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = log_monitor("log:./docker/test-data/sample.logfile")
    cfg = builder.build_config()
    print_config_summary(cfg, title="Log Monitor")
    print(f"Goal: {cfg.goal[:70]}...")
    print("\nTo run with live monitoring:")
    print_to_run_hint("log_monitor", '"log:./app.log"')
