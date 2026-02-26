# Example: Security Audit

Automated security analysis of code using TOON format + LLM.

## Quick Start

```bash
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --goal "security audit: find hardcoded secrets, SQL injection, XSS, CSRF, authentication bypass, insecure dependencies" \
  --model google/gemini-3-flash-preview \
  --interval 0
```

## What It Detects

- Hardcoded API keys, passwords, tokens
- SQL injection vulnerabilities
- Missing input validation
- Insecure authentication patterns
- Unhandled exceptions that leak info
- Missing HTTPS/TLS enforcement

## Review Results

```bash
python -m toonic.server.client
toonic> history 20
toonic> query "findings with high confidence"
toonic> sql SELECT target_path, content FROM exchanges WHERE action_type='alert'
```
