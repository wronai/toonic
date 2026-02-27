#!/usr/bin/env python3
"""
Infrastructure Monitoring — run with: python examples/infra-monitoring/run.py

Before: ~25 lines of manual config + trigger YAML loading.
After:  3 lines with preset.
"""
from toonic.server.quick import infra_health

if __name__ == "__main__":
    builder = infra_health("docker:*", "net:8.8.8.8,1.1.1.1")
    cfg = builder.build_config()
    print(f"Infra Health: {len(cfg.sources)} sources, interval={cfg.interval}s")
    print(f"Goal: {cfg.goal[:70]}...")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run:")
    print('  from toonic.server.quick import infra_health')
    print('  infra_health("docker:*", "db:./app.db", "net:8.8.8.8").run()')
