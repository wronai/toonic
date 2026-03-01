"""
Quick-start helpers — one-liner functions for common monitoring scenarios.

This module re-exports all components from the quick subpackage.
"""

# Re-export all public API from submodules
from toonic.server.quick.parsing import parse_source, _PREFIX_CATEGORY, _PROTO_CATEGORY
from toonic.server.quick.archive import unpack_archive, watch_archive
from toonic.server.quick.builder import ConfigBuilder
from toonic.server.quick.presets import (
    security_audit,
    code_review,
    log_monitor,
    infra_health,
    cctv_monitor,
    web_monitor,
    full_stack,
    PRESETS,
)
from toonic.server.quick.runtime import watch, monitor, serve, run

__all__ = [
    # Parsing
    "parse_source",
    "_PREFIX_CATEGORY",
    "_PROTO_CATEGORY",
    # Archive
    "unpack_archive",
    "watch_archive",
    # Builder
    "ConfigBuilder",
    # Runtime
    "watch",
    "monitor",
    "serve",
    "run",
    # Presets
    "security_audit",
    "code_review",
    "log_monitor",
    "infra_health",
    "cctv_monitor",
    "web_monitor",
    "full_stack",
    "PRESETS",
]
