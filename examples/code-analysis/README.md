# Example: Code Analysis

Analyze a sample Python project for bugs, security issues, and quality improvements.
Uses `CodeAnalysisPrompt` — a TOON-aware prompt builder that understands the compact
notation and produces structured findings with file/line references.

## Quick Start

```bash
# Start server analyzing the sample project
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --goal "find bugs, security issues, and suggest improvements" \
  --interval 0

# Open http://localhost:8900 for Web UI
```

## Continuous Analysis (watch mode)

```bash
# Re-analyze every 60s — detects file changes via delta TOON
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --goal "code review: find bugs, security issues, suggest improvements" \
  --interval 60

# Combine with log monitoring for full-stack analysis
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --source log:./app.log \
  --goal "correlate code issues with runtime errors" \
  --interval 30
```

## Using CLI Shell

```bash
python -m toonic.server.client
toonic> status
toonic> analyze find all security vulnerabilities
toonic> convert examples/code-analysis/sample-project/main.py toon
toonic> history 10
toonic> query "findings with high severity"
toonic> sql SELECT target_path, content FROM exchanges WHERE action_type='code_fix'
```

## How It Works

1. **FileWatcher** scans `sample-project/` and converts to TOON format
2. **LLM Pipeline** auto-selects `CodeAnalysisPrompt` (detects code category + goal keywords)
3. `CodeAnalysisPrompt` builds TOON-aware prompt: explains M/c/f/m/i/e notation to LLM
4. LLM returns structured JSON with `findings[]` — file, line, severity, description, fix
5. **ResponseParser** extracts JSON from markdown fences or raw response
6. Results stored in `toonic_data/history.db` and shown in Web UI

### Prompt Builder Selection

The `select_prompt_builder()` function auto-selects based on goal + data categories:

| Condition | Builder | Optimized for |
|-----------|---------|---------------|
| Video sources + CCTV keywords | `CCTVEventPrompt` | Event analysis |
| Code/config sources or code keywords | `CodeAnalysisPrompt` | TOON-aware code review |
| Everything else | `GenericPrompt` | General analysis |

## Expected Findings

The sample project has intentional issues:
- **Bug**: `deactivate_user()` — no existence check, KeyError on missing user
- **Bug**: `create_order()` — no validation on `total`, could be negative
- **Security**: `process_payment()` — hardcoded API key
- **Performance**: `get_orders()` — O(n) linear scan instead of indexed lookup

## Files in This Example

- **`README.md`** — this file
- **`sample-project/main.py`** — Python code with intentional bugs
- **`sample-project/config.py`** — Config file with hardcoded secrets
