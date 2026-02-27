#!/usr/bin/env python3
"""Security audit (web) — run with: python examples/security-audit-web/run.py"""

from toonic.server.quick import security_audit
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = (
        security_audit("http://httpbin.org/")
        .network("httpbin.org")
        .goal(
            "web security audit: OWASP Top 10, security headers, TLS config, "
            "exposed endpoints, input validation"
        )
    )
    cfg = builder.build_config()
    print_config_summary(cfg, title="Security Audit (web)")
    print_to_run_hint("security_audit", '"https://example.com"')
    print("  .network('example.com').run()")
