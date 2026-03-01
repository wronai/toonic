"""
Quick-start helpers — one-liner functions for common monitoring scenarios.

Usage:
    from toonic.server.quick import monitor, watch, serve

    # One-liner: monitor logs
    await monitor("log:./app.log", goal="detect errors")

    # Fluent builder
    srv = (
        watch("./src/", category="code")
        .add("log:./app.log")
        .add("docker:*")
        .add("net:8.8.8.8,1.1.1.1")
        .goal("full-stack monitoring")
        .when("error occurs 5 times in 60 seconds")
        .interval(30)
        .build()
    )
    await serve(srv)

This module is a backward-compatible shim that re-exports from the quick package.
"""

# Re-export all public API from the quick subpackage
from toonic.server.quick import (
    ConfigBuilder,
    PRESETS,
    _PREFIX_CATEGORY,
    _PROTO_CATEGORY,
    cctv_monitor,
    code_review,
    full_stack,
    infra_health,
    log_monitor,
    monitor,
    parse_source,
    run,
    security_audit,
    serve,
    unpack_archive,
    watch,
    watch_archive,
    web_monitor,
)

__all__ = [
    "ConfigBuilder",
    "PRESETS",
    "_PREFIX_CATEGORY",
    "_PROTO_CATEGORY",
    "cctv_monitor",
    "code_review",
    "full_stack",
    "infra_health",
    "log_monitor",
    "monitor",
    "parse_source",
    "run",
    "security_audit",
    "serve",
    "unpack_archive",
    "watch",
    "watch_archive",
    "web_monitor",
]
