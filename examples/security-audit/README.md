# Example: Security Audit

Automated security analysis of code using TOON format + LLM.
Combines `CodeAnalysisPrompt` with security-focused goals and optional
log correlation for runtime vulnerability detection.

## Quick Start — One-Shot Audit

```bash
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --goal "security audit: find hardcoded secrets, SQL injection, XSS, CSRF, authentication bypass, insecure dependencies" \
  --model google/gemini-2.5-flash-preview:thinking \
  --interval 0
```

## Continuous Security Monitoring

```bash
# Watch for security issues as code changes
python -m toonic.server \
  --source file:./src/ \
  --source log:./logs/access.log \
  --goal "security monitoring: detect new vulnerabilities, suspicious log patterns, unauthorized access attempts" \
  --when "when error occurs 3 times in 30 seconds, otherwise every 5 minutes"
```

## Multi-Source Security Audit

```bash
# Audit code + check for exposed services + monitor logs
python -m toonic.server \
  --source file:./src/ \
  --source log:./logs/auth.log \
  --source "net:api.example.com" \
  --source port:5432 \
  --goal "comprehensive security audit: code vulnerabilities, exposed services, auth failures, network security" \
  --interval 60
```

## What It Detects

- **Code**: hardcoded API keys, passwords, tokens
- **Code**: SQL injection, XSS, CSRF vulnerabilities
- **Code**: missing input validation, insecure deserialization
- **Code**: insecure authentication patterns, privilege escalation
- **Code**: unhandled exceptions that leak stack traces
- **Logs**: failed authentication attempts, brute force patterns
- **Logs**: suspicious access patterns, unusual IP addresses
- **Network**: exposed ports, unencrypted connections

## Review Results

```bash
python -m toonic.server.client
toonic> history 20
toonic> query "findings with high confidence"
toonic> query "critical security vulnerabilities"
toonic> sql SELECT target_path, content FROM exchanges WHERE action_type='alert' ORDER BY confidence DESC
toonic> sql SELECT action_type, COUNT(*) FROM exchanges GROUP BY action_type
```

## Priority in Security Context

When combining code + logs, the Accumulator ensures:
- **CRITICAL log lines** (auth failures, crashes) → priority 1.0, always in LLM context
- **ERROR log lines** → priority 0.8
- **Code chunks** → priority 0.5 (normal)
- **INFO/DEBUG logs** → priority 0.1–0.3, evicted first

This means the LLM always sees the most security-relevant data, even under tight token budgets.
