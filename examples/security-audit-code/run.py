#!/usr/bin/env python3
"""Security audit (code) — run with: python examples/security-audit-code/run.py"""

from toonic.server.quick import security_audit
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = security_audit("./examples/code-analysis/sample-project/")
    cfg = builder.build_config()
    print_config_summary(cfg, title="Security Audit (code)")
    print_to_run_hint("security_audit", '"./src/"')
