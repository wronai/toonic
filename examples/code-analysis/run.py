#!/usr/bin/env python3
"""
Code Analysis — run with: python examples/code-analysis/run.py

Before (manual): ~15 lines of ServerConfig + ToonicServer setup.
After (preset):  2 lines.
"""
from toonic.server.quick import code_review

if __name__ == "__main__":
    # Dry config build (no server start) — safe to run
    builder = code_review("./examples/code-analysis/sample-project/")
    cfg = builder.build_config()
    print(f"Code Review: {len(cfg.sources)} sources, goal={cfg.goal[:60]}...")
    print("\nTo actually run:")
    print('  from toonic.server.quick import code_review')
    print('  code_review("./src/").run()')
