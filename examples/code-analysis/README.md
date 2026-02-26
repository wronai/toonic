# Example: Code Analysis

Analyze a sample Python project for bugs, security issues, and quality improvements.

## Quick Start

```bash
# Start server analyzing the sample project
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --goal "find bugs, security issues, and suggest improvements" \
  --interval 0

# Open http://localhost:8900 for Web UI
```

## Using CLI Shell

```bash
python -m toonic.server.client
toonic> status
toonic> analyze find all security vulnerabilities
toonic> convert examples/code-analysis/sample-project/main.py toon
```

## Expected Findings

The sample project has intentional issues:
- **Bug**: `deactivate_user()` — no existence check, KeyError on missing user
- **Bug**: `create_order()` — no validation on `total`, could be negative
- **Security**: `process_payment()` — hardcoded API key
- **Performance**: `get_orders()` — O(n) linear scan instead of indexed lookup
