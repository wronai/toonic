#!/usr/bin/env python3
"""Full-stack security audit (dry build) — run with: python examples/security-audit-fullstack/run.py"""

from toonic.server.quick import security_audit

if __name__ == "__main__":
    builder = (
        security_audit(
            "./examples/code-analysis/sample-project/",
            "log:./docker/test-data/sample.logfile",
        )
        .network("api.example.com")
        .database("db:./app.db")
        .process("port:5432")
        .goal(
            "comprehensive security audit: code vulnerabilities, auth log failures, "
            "exposed services, database security"
        )
    )
    cfg = builder.build_config()
    print(f"Security Audit (full-stack): {len(cfg.sources)} sources")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run on your stack:")
    print('  from toonic.server.quick import security_audit')
    print('  security_audit("./src/", "log:./auth.log").network("api.example.com").database("db:./app.db").run()')
