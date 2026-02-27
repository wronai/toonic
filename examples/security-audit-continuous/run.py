#!/usr/bin/env python3
"""Continuous security monitoring (dry build) — run with: python examples/security-audit-continuous/run.py"""

from toonic.server.quick import security_audit

if __name__ == "__main__":
    builder = (
        security_audit(
            "./examples/code-analysis/sample-project/",
            "log:./docker/test-data/sample.logfile",
        )
        .interval(300)
        .goal(
            "continuous security monitoring: detect new vulnerabilities, "
            "suspicious log patterns, unauthorized access attempts"
        )
    )
    cfg = builder.build_config()
    print(f"Security Monitoring (continuous): interval={cfg.interval}s, sources={len(cfg.sources)}")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run continuously:")
    print('  from toonic.server.quick import security_audit')
    print('  security_audit("./src/", "log:./app.log").interval(300).run()')
