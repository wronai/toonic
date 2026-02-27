#!/usr/bin/env python3
"""
Log Monitoring — run with: python examples/log-monitoring/run.py

Before: ~20 lines of manual ServerConfig + trigger setup.
After:  2 lines with preset.
"""
from toonic.server.quick import log_monitor

if __name__ == "__main__":
    builder = log_monitor("log:./docker/test-data/sample.logfile")
    cfg = builder.build_config()
    print(f"Log Monitor: {len(cfg.sources)} sources, interval={cfg.interval}s")
    print(f"Goal: {cfg.goal[:70]}...")
    print("\nTo run with live monitoring:")
    print('  from toonic.server.quick import log_monitor')
    print('  log_monitor("log:./app.log").run()')
