#!/usr/bin/env python3
"""Continuous security monitoring (dry build) — run with: python examples/security-audit-continuous/run.py"""

from toonic.server.quick import security_audit
from examples._helpers import print_config_summary, print_to_run_hint


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
    print_config_summary(cfg, title="Security Monitoring (continuous)")
    print_to_run_hint("security_audit", '"./src/", "log:./app.log"')
    print("  .interval(300).run()")
