#!/usr/bin/env python3

from __future__ import annotations

from toonic.server.quick import watch


SCENARIOS = {
    "http_net_proc": [
        "https://httpbin.org/get",
        "net:8.8.8.8,1.1.1.1",
        "proc:nginx",
    ],
    "rtsp_logs": [
        "rtsp://localhost:8554/test-cam1",
        "log:./docker/test-data/sample.logfile",
    ],
    "db_urls": [
        "postgresql://user:pass@db:5432/app",
        "mysql://user:pass@db:3306/app",
        "redis://cache:6379",
        "mongodb://mongo:27017/app",
    ],
    "infra_prefixes": [
        "docker:*",
        "dir:./examples/",
        "port:8080",
        "tcp:db:5432",
    ],
}


def main() -> None:
    for name, sources in SCENARIOS.items():
        cfg = watch(*sources).goal(f"scenario={name}").interval(0).build_config()
        print(f"\n=== {name} ===")
        print(f"sources: {len(cfg.sources)}")
        for src in cfg.sources:
            print(f"  [{src.category:10}] {src.path_or_url}")


if __name__ == "__main__":
    main()
