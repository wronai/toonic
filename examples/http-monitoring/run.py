#!/usr/bin/env python3
"""
HTTP/API Monitoring — run with: python examples/http-monitoring/run.py

Before: ~20 lines of manual config with HttpWatcher options.
After:  2 lines with preset.
"""
from toonic.server.quick import web_monitor

if __name__ == "__main__":
    builder = web_monitor("https://httpbin.org/get", "https://httpbin.org/status/200")
    cfg = builder.build_config()
    print(f"Web Monitor: {len(cfg.sources)} endpoints, interval={cfg.interval}s")
    print(f"Goal: {cfg.goal[:70]}...")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run:")
    print('  from toonic.server.quick import web_monitor')
    print('  web_monitor("https://api.example.com/health").run()')
