#!/usr/bin/env python3
"""Full-stack security audit (dry build) — run with: python examples/security-audit-fullstack/run.py"""

from toonic.server.quick import security_audit
from examples._helpers import print_config_summary, print_to_run_hint


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
    print_config_summary(cfg, title="Security Audit (full-stack)")
    print_to_run_hint("security_audit", '"./src/", "log:./auth.log"')
    print("  .network('api.example.com').database('db:./app.db').run()")
