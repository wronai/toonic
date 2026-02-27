#!/usr/bin/env python3
"""Security audit (web) — run with: python examples/security-audit-web/run.py"""

from toonic.server.quick import security_audit

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
    print(f"Security Audit (web): {len(cfg.sources)} sources")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run on your site:")
    print('  from toonic.server.quick import security_audit')
    print('  security_audit("https://example.com").network("example.com").run()')
