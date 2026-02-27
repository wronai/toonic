#!/usr/bin/env python3
"""Security audit (code) — run with: python examples/security-audit-code/run.py"""

from toonic.server.quick import security_audit

if __name__ == "__main__":
    builder = security_audit("./examples/code-analysis/sample-project/")
    cfg = builder.build_config()
    print(f"Security Audit (code): {len(cfg.sources)} sources")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run on your repo:")
    print('  from toonic.server.quick import security_audit')
    print('  security_audit("./src/").run()')
