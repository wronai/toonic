#!/usr/bin/env python3
"""
DB + Archive triage — run with: python examples/db-archive-triage/run.py
"""
from pathlib import Path

from toonic.server.quick import unpack_archive, watch


if __name__ == "__main__":
    archive = Path("./examples/archive-monitoring/sample-bundle.zip")
    # Keep script dry: if sample archive is missing, use examples dir fallback.
    if archive.exists():
        extracted = unpack_archive(archive)
        dir_source = f"dir:{extracted}"
    else:
        dir_source = "dir:./examples/"

    cfg = (
        watch(
            "postgresql://user:pass@db:5432/app",
            "mysql://user:pass@db:3306/app",
            "redis://cache:6379",
            dir_source,
        )
        .goal("triage db sources and extracted incident artifacts")
        .interval(60)
        .build_config()
    )

    print(f"sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"  [{s.category:10}] {s.path_or_url}")
