#!/usr/bin/env python3
"""
Security Audit — simplified using Toonic presets.

Replaces 500+ lines of custom code with Toonic's built-in watchers.
Each function below is a complete, runnable security audit.

Usage:
    python examples/security-audit/quick_audit.py
"""

from __future__ import annotations


def audit_code(path: str = "./examples/code-analysis/sample-project/"):
    """One-shot code security audit — finds secrets, injections, OWASP issues.

    Before (continuous_monitoring.py): 524 lines, custom aiohttp, ssl, smtplib.
    After: 2 lines using Toonic preset.
    """
    from toonic.server.quick import security_audit
    # One-liner: builds ServerConfig with security-focused goal + one-shot interval
    return security_audit(path)


def audit_website(url: str = "http://obywatel.bielik.ai/"):
    """Website security audit — headers, SSL, content, endpoints.

    Before (enterprise_features.py): 718 lines, custom ML, threat intel.
    After: 5 lines using Toonic's built-in watchers.
    """
    from toonic.server.quick import security_audit
    return (
        security_audit(url)
        .network(url.split("//")[1].rstrip("/"))
        .goal("web security audit: OWASP Top 10, security headers, "
              "TLS config, exposed endpoints, input validation")
    )


def continuous_monitoring(path: str = "./src/", log: str = "log:./app.log"):
    """Continuous security monitoring with triggers.

    Before: custom daemon loop with asyncio.sleep, email alerts, webhook.
    After: Toonic's built-in trigger scheduler + watchers handle everything.
    """
    from toonic.server.quick import security_audit
    return (
        security_audit(path, log)
        .network("api.example.com")
        .process("port:5432")
        .interval(300)
        .goal("continuous security monitoring: detect new vulnerabilities, "
              "suspicious log patterns, unauthorized access attempts")
    )


def full_stack_audit(
    code: str = "./src/",
    logs: str = "log:./auth.log",
    network: str = "api.example.com",
    db: str = "db:./app.db",
):
    """Full-stack security audit: code + logs + network + database.

    Before: required combining continuous_monitoring.py + enterprise_features.py
    + generate_report.py (1400+ lines total).
    After: 8 lines, all watchers built-in.
    """
    from toonic.server.quick import security_audit
    return (
        security_audit(code, logs)
        .network(network)
        .database(db)
        .process("port:5432")
        .goal("comprehensive security audit: code vulnerabilities, "
              "auth log failures, exposed services, database security")
    )


def demo():
    """Demo: build configs without starting server (safe to run)."""
    print("=" * 60)
    print("  Security Audit — Toonic Presets Demo")
    print("=" * 60)

    # 1. Code audit
    print("\n1. Code Security Audit (1-liner)")
    builder = audit_code()
    cfg = builder.build_config()
    print(f"   Goal:    {cfg.goal[:70]}...")
    print(f"   Sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"     [{s.category}] {s.path_or_url}")

    # 2. Website audit
    print("\n2. Website Security Audit")
    builder = audit_website("http://httpbin.org/")
    cfg = builder.build_config()
    print(f"   Goal:    {cfg.goal[:70]}...")
    print(f"   Sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"     [{s.category}] {s.path_or_url}")

    # 3. Continuous monitoring
    print("\n3. Continuous Monitoring")
    builder = continuous_monitoring(
        "./examples/code-analysis/sample-project/",
        "log:./docker/test-data/sample.logfile",
    )
    cfg = builder.build_config()
    print(f"   Goal:    {cfg.goal[:70]}...")
    print(f"   Interval: {cfg.interval}s")
    print(f"   Sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"     [{s.category}] {s.path_or_url}")

    # 4. Full-stack
    print("\n4. Full-Stack Security Audit")
    builder = full_stack_audit(
        code="./examples/code-analysis/sample-project/",
        logs="log:./docker/test-data/sample.logfile",
    )
    cfg = builder.build_config()
    print(f"   Goal:    {cfg.goal[:70]}...")
    print(f"   Sources: {len(cfg.sources)}")
    for s in cfg.sources:
        print(f"     [{s.category}] {s.path_or_url}")

    print("\n" + "=" * 60)
    print("  To actually run any audit:")
    print("    from toonic.server.quick import security_audit")
    print('    security_audit("./src/").run()')
    print("=" * 60)


if __name__ == "__main__":
    demo()
