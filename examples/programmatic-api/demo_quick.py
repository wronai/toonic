#!/usr/bin/env python3
"""
Demo: Quick-start API — build monitoring configs in one line.

Shows how toonic.server.quick simplifies source parsing, config building,
and server instantiation with the fluent ConfigBuilder API.

Usage:
    python examples/programmatic-api/demo_quick.py
"""

from toonic.server.quick import ConfigBuilder, parse_source, watch


def demo_parse_source():
    """Show automatic source type detection."""
    print("=" * 60)
    print("1. Automatic Source Detection (parse_source)")
    print("=" * 60)

    examples = [
        # Prefix-based
        "log:./app.log",
        "docker:*",
        "db:./app.db",
        "net:8.8.8.8,1.1.1.1",
        "proc:nginx",
        "port:5432",
        # Protocol-based
        "rtsp://192.168.1.100:554/stream",
        "http://api.example.com/health",
        "postgresql://user:pass@db:5432/mydb",
        # Extension-based (plain paths)
        "./src/main.py",
        "./app.log",
        "./data.csv",
        "./config.yaml",
        "./report.pdf",
        "./video.mp4",
        # Directories
        "./src/",
    ]

    for s in examples:
        src = parse_source(s)
        print(f"  {s:50s} → category={src.category:12s} path={src.path_or_url}")


def demo_config_builder():
    """Show fluent ConfigBuilder API."""
    print("\n" + "=" * 60)
    print("2. Fluent ConfigBuilder")
    print("=" * 60)

    # Method 1: using .add() with auto-detection
    cfg1 = (
        ConfigBuilder()
        .add("./src/")
        .add("log:./app.log")
        .add("docker:*")
        .add("net:8.8.8.8")
        .goal("full-stack monitoring")
        .interval(30)
        .port(9000)
        .build_config()
    )
    print(f"\n  Config 1 (auto-detect): {len(cfg1.sources)} sources")
    for s in cfg1.sources:
        print(f"    [{s.category:12s}] {s.path_or_url}")

    # Method 2: using typed methods
    cfg2 = (
        ConfigBuilder()
        .code("./src/")
        .logs("./app.log")
        .docker("my-app")
        .database("db:./app.db")
        .network("8.8.8.8,1.1.1.1")
        .process("proc:nginx")
        .http("https://api.example.com/health")
        .directory("./data/")
        .goal("infrastructure health")
        .interval(15)
        .tokens(80000, {"code": 0.2, "logs": 0.3, "video": 0.1, "system": 0.4})
        .model("google/gemini-2.5-flash-preview:thinking")
        .build_config()
    )
    print(f"\n  Config 2 (typed methods): {len(cfg2.sources)} sources")
    for s in cfg2.sources:
        print(f"    [{s.category:12s}] {s.path_or_url}")
    print(f"  Token budget: {cfg2.max_context_tokens}")
    print(f"  Allocation:   {cfg2.token_allocation}")


def demo_watch():
    """Show the watch() one-liner."""
    print("\n" + "=" * 60)
    print("3. watch() One-Liner")
    print("=" * 60)

    # Build server in one chain
    server = (
        watch("./src/", "log:./app.log", "docker:*")
        .goal("find bugs + monitor errors + check containers")
        .interval(30)
        .no_history()
        .build()
    )
    print(f"\n  Server built: {len(server.config.sources)} sources")
    print(f"  Goal: {server.config.goal}")
    print(f"  Interval: {server.config.interval}s")
    for s in server.config.sources:
        print(f"    [{s.category:12s}] {s.path_or_url}")


def demo_options():
    """Show passing extra options to sources."""
    print("\n" + "=" * 60)
    print("4. Source Options")
    print("=" * 60)

    server = (
        watch()
        .add("log:./app.log", poll_interval=2, max_lines=1000)
        .add("rtsp://cam:554/stream", detect_objects="true", detect_classes="person,car")
        .video("rtsp://cam2:554/stream", detect_model="yolov8n.pt", min_event_frames=3)
        .docker("*", track_logs="true", log_tail=20)
        .database("db:./app.db", track_schema="true", track_row_counts="true")
        .network("8.8.8.8,1.1.1.1", check_dns="true", timeout=5)
        .goal("multi-source monitoring with custom options")
        .build()
    )
    print(f"\n  Server built: {len(server.config.sources)} sources")
    for s in server.config.sources:
        opts = dict(s.options) if s.options else {}
        print(f"    [{s.category:12s}] {s.path_or_url:40s} opts={opts}")


def main():
    demo_parse_source()
    demo_config_builder()
    demo_watch()
    demo_options()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)
    print("\nTo actually run a server:")
    print('  from toonic.server.quick import run')
    print('  run("./src/", "log:./app.log", goal="find bugs")')


if __name__ == "__main__":
    main()
