#!/usr/bin/env python3
"""
HTTP/API Monitoring — run with: python examples/http-monitoring/run.py

Before: ~20 lines of manual config with HttpWatcher options.
After:  2 lines with preset.
"""
from toonic.server.quick import web_monitor
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = web_monitor("https://httpbin.org/get", "https://httpbin.org/status/200")
    cfg = builder.build_config()
    print_config_summary(cfg, title="Web Monitor")
    print(f"Goal: {cfg.goal[:70]}...")
    print_to_run_hint("web_monitor", '"https://api.example.com/health"')
