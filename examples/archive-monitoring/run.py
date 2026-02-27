#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

from toonic.server.quick import watch_archive
from examples._helpers import print_config_summary, print_to_run_hint


def main() -> None:
    # Demo archive path (adjust as needed)
    archive = "./bundle.zip"
    if not Path(archive).exists():
        # Fallback: create a tiny archive-like workflow hint in the README
        # (This script is intentionally lightweight; it does not create archives.)
        print(f"Archive not found: {archive}")
        print("Provide an archive path as ./bundle.zip or edit examples/archive-monitoring/run.py")
        return

    server = (
        watch_archive(archive, include_files_as_sources=True)
        .goal("security audit: scan extracted files for secrets, insecure configs, vulnerable patterns")
        .interval(0)
        .build()
    )

    # Note: this builds config; starting the server is intentionally omitted to keep it runnable offline.
    cfg = server.config
    print_config_summary(cfg, title="Archive Monitor")
    print(f"Goal: {cfg.goal[:70]}...")
    print_to_run_hint("watch_archive", '"./bundle.zip"')


if __name__ == "__main__":
    main()
