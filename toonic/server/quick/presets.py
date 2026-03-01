"""
Pre-configured monitoring scenario presets.
"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from toonic.server.quick.builder import ConfigBuilder


_PRESET_SECURITY_GOAL = (
    "security audit: hardcoded secrets, SQL injection, XSS, CSRF, "
    "auth bypass, insecure dependencies, exposed endpoints"
)

_PRESET_CODE_REVIEW_GOAL = (
    "code review: find bugs, dead code, performance issues, "
    "SOLID violations, suggest improvements with file/line refs"
)

_PRESET_LOG_MONITOR_GOAL = (
    "log monitoring: detect error spikes, anomaly patterns, "
    "correlate failures, suggest root cause and fixes"
)

_PRESET_INFRA_HEALTH_GOAL = (
    "infrastructure health: container status, database integrity, "
    "network connectivity, service availability, resource usage"
)

_PRESET_CCTV_MONITOR_GOAL = (
    "CCTV security: detect intrusions, describe person/vehicle actions, "
    "classify events as normal/suspicious/intrusion, note directions"
)

_PRESET_WEB_MONITOR_GOAL = (
    "web monitoring: uptime, response times, SSL expiry, "
    "content changes, security headers, status code anomalies"
)

_PRESET_FULL_STACK_GOAL = (
    "full-stack monitoring: code quality, log anomalies, "
    "container health, database integrity, network connectivity"
)


def _apply_overrides(builder: "ConfigBuilder", overrides: Dict[str, Any]) -> None:
    """Apply override kwargs to builder instance."""
    for k, v in overrides.items():
        if hasattr(builder, k):
            getattr(builder, k)(v)


def security_audit(*sources: str, **overrides) -> "ConfigBuilder":
    """Pre-configured security audit preset.

    Usage:
        from toonic.server.quick import security_audit
        security_audit("./src/").run()                    # async
        security_audit("./src/", "log:./auth.log").run()  # multi-source
    """
    from toonic.server.quick.runtime import watch

    builder = watch(*sources) if sources else watch()
    builder.goal(overrides.pop("goal", _PRESET_SECURITY_GOAL))
    builder.interval(overrides.pop("interval", 0))
    _apply_overrides(builder, overrides)
    return builder


def code_review(*sources: str, **overrides) -> "ConfigBuilder":
    """Pre-configured code review preset.

    Usage:
        from toonic.server.quick import code_review
        code_review("./src/").run()
    """
    from toonic.server.quick.runtime import watch

    builder = watch(*sources) if sources else watch()
    builder.goal(overrides.pop("goal", _PRESET_CODE_REVIEW_GOAL))
    builder.interval(overrides.pop("interval", 0))
    _apply_overrides(builder, overrides)
    return builder


def log_monitor(*sources: str, **overrides) -> "ConfigBuilder":
    """Pre-configured log monitoring preset.

    Usage:
        from toonic.server.quick import log_monitor
        log_monitor("log:./app.log").run()
    """
    from toonic.server.quick.runtime import watch

    builder = watch(*sources) if sources else watch()
    builder.goal(overrides.pop("goal", _PRESET_LOG_MONITOR_GOAL))
    builder.interval(overrides.pop("interval", 10))
    _apply_overrides(builder, overrides)
    return builder


def infra_health(*sources: str, **overrides) -> "ConfigBuilder":
    """Pre-configured infrastructure health monitoring preset.

    Usage:
        from toonic.server.quick import infra_health
        infra_health("docker:*", "db:./app.db", "net:8.8.8.8").run()
    """
    from toonic.server.quick.runtime import watch

    builder = watch(*sources) if sources else watch()
    builder.goal(overrides.pop("goal", _PRESET_INFRA_HEALTH_GOAL))
    builder.interval(overrides.pop("interval", 30))
    _apply_overrides(builder, overrides)
    return builder


def cctv_monitor(*sources: str, **overrides) -> "ConfigBuilder":
    """Pre-configured CCTV/video monitoring preset.

    Usage:
        from toonic.server.quick import cctv_monitor
        cctv_monitor("rtsp://cam:554/stream").run()
    """
    from toonic.server.quick.runtime import watch

    builder = watch(*sources) if sources else watch()
    builder.goal(overrides.pop("goal", _PRESET_CCTV_MONITOR_GOAL))
    builder.interval(overrides.pop("interval", 0))
    _apply_overrides(builder, overrides)
    return builder


def web_monitor(*urls: str, **overrides) -> "ConfigBuilder":
    """Pre-configured web/API endpoint monitoring preset.

    Usage:
        from toonic.server.quick import web_monitor
        web_monitor("https://api.example.com/health").run()
    """
    from toonic.server.quick.builder import ConfigBuilder

    builder = ConfigBuilder()
    for url in urls:
        builder.http(url)
    builder.goal(overrides.pop("goal", _PRESET_WEB_MONITOR_GOAL))
    builder.interval(overrides.pop("interval", 60))
    _apply_overrides(builder, overrides)
    return builder


def full_stack(*sources: str, **overrides) -> "ConfigBuilder":
    """Pre-configured full-stack monitoring preset.

    Usage:
        from toonic.server.quick import full_stack
        full_stack("./src/", "log:./app.log", "docker:*", "db:./app.db").run()
    """
    from toonic.server.quick.runtime import watch

    builder = watch(*sources) if sources else watch()
    builder.goal(overrides.pop("goal", _PRESET_FULL_STACK_GOAL))
    builder.interval(overrides.pop("interval", 30))
    _apply_overrides(builder, overrides)
    return builder


# Registry of all presets (for CLI discovery)
PRESETS: Dict[str, Any] = {
    "security-audit": {"fn": security_audit, "desc": "Security audit: secrets, injections, OWASP Top 10"},
    "code-review": {"fn": code_review, "desc": "Code review: bugs, SOLID, performance"},
    "log-monitor": {"fn": log_monitor, "desc": "Log monitoring: error spikes, anomalies"},
    "infra-health": {"fn": infra_health, "desc": "Infrastructure: Docker, DB, network, processes"},
    "cctv-monitor": {"fn": cctv_monitor, "desc": "CCTV/video: intrusion detection, event analysis"},
    "web-monitor": {"fn": web_monitor, "desc": "Web/API: uptime, response times, SSL, headers"},
    "full-stack": {"fn": full_stack, "desc": "Full-stack: code + logs + infra + network"},
}
