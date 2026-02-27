#!/usr/bin/env python3
"""
Infra triage recipes — run with: python examples/infra-triage/run.py
"""
from toonic.server.quick import watch


if __name__ == "__main__":
    cfg = (
        watch(
            "docker:*",
            "net:8.8.8.8,1.1.1.1",
            "proc:nginx",
            "port:5432",
            "dir:./examples/",
            "log:./docker/test-data/sample.logfile",
        )
        .goal("triage infra signals across container, network, process, directory and logs")
        .interval(30)
        .build_config()
    )

    print(f"sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"  [{s.category:10}] {s.path_or_url}")
