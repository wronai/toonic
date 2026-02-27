# Example: Security Audit

Automated security analysis of code using TOON format + LLM.
Combines `CodeAnalysisPrompt` with security-focused goals and optional
log correlation for runtime vulnerability detection.

## Quick Start (Python — 1 line)

```python
from toonic.server.quick import run
run("./src/", goal="security audit: hardcoded secrets, SQL injection, XSS, CSRF, auth bypass", interval=0)
```

## Quick Start (fluent builder)

```python
from toonic.server.quick import watch

server = (
    watch()
    .code("./src/")
    .logs("./logs/auth.log")
    .network("api.example.com")
    .process("port:5432")
    .goal("security audit: code + exposed services + auth failures + network")
    .interval(60)
    .build()
)
```

## Quick Start — One-Shot Audit (CLI)

```bash
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --goal "security audit: find hardcoded secrets, SQL injection, XSS, CSRF, authentication bypass, insecure dependencies" \
  --model google/gemini-2.5-flash-preview:thinking \
  --interval 0
```

## Continuous Security Monitoring

```bash
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

## Website Security Audit - obywatel.bielik.ai

### Quick Start (Python — 1 line)

```python
from toonic.server.quick import run
run("http://obywatel.bielik.ai/", goal="security audit: web vulnerabilities, TLS issues, exposed endpoints, data leaks", interval=0)
```

### Comprehensive Website Security Audit

```python
from toonic.server.quick import watch

server = (
    watch("http://obywatel.bielik.ai/")
    .network("obywatel.bielik.ai")
    .http("http://obywatel.bielik.ai/")
    .goal("complete web security audit: OWASP Top 10, TLS configuration, headers, exposed APIs, data validation")
    .interval(30)
    .build()
)
```

### CLI Commands

```bash
# One-shot security audit of the website (use HTTP if SSL issues)
python -m toonic.server \
  --source "http://obywatel.bielik.ai/" \
  --goal "security audit: OWASP Top 10 vulnerabilities, security headers, TLS configuration, exposed endpoints, input validation" \
  --model google/gemini-3-flash-preview \
  --interval 0

# With custom port (if 8901 is occupied)
python -m toonic.server \
  --source "http://obywatel.bielik.ai/" \
  --goal "security audit: OWASP Top 10 vulnerabilities, security headers, TLS configuration, exposed endpoints, input validation" \
  --model google/gemini-3-flash-preview \
  --interval 0 \
  --port 8902

# Alternative: SSL/TLS focused analysis
python -m toonic.server \
  --source "net:obywatel.bielik.ai" \
  --source "port:443" \
  --goal "SSL/TLS security analysis: certificate issues, cipher suites, protocol versions" \
  --model google/gemini-3-flash-preview \
  --interval 0

# Alternative: Process-based port monitoring
python -m toonic.server \
  --source "port:443" \
  --source "tcp:obywatel.bielik.ai:443" \
  --goal "Port 443 security analysis: SSL handshake, service availability" \
  --model google/gemini-3-flash-preview \
  --interval 0

# Continuous monitoring of the website
python -m toonic.server \
  --source "http://obywatel.bielik.ai/" \
  --source "net:obywatel.bielik.ai" \
  --goal "website security monitoring: detect new vulnerabilities, security misconfigurations, certificate issues" \
  --interval 3600
```

**Note**: If you encounter SSL/TLS errors like `[SSL: TLSV1_ALERT_INTERNAL_ERROR]`, use HTTP instead of HTTPS or analyze SSL/TLS separately using network and process monitoring. The `net:` prefix provides network connectivity analysis while `port:` and `tcp:` prefixes give you port-specific security monitoring.

**Port Conflicts**: If port 8901 is occupied, use `--port 8902` or another available port.

### What It Checks for obywatel.bielik.ai

- **OWASP Top 10**: SQL injection, XSS, CSRF, security misconfigurations
- **TLS/SSL**: Certificate validity, weak ciphers, protocol versions (use network monitoring for SSL issues)
- **Security Headers**: HSTS, CSP, X-Frame-Options, CORS policies
- **Exposed Endpoints**: API discovery, admin panels, debug interfaces
- **Data Validation**: Input sanitization, parameter pollution
- **Authentication**: Session management, password policies, MFA
- **Information Disclosure**: Error messages, server signatures, directory listings
- **Network Security**: Open ports, services, DNS configurations

**Known Issues**: The website has SSL/TLS configuration problems (`TLSV1_ALERT_INTERNAL_ERROR`). Use HTTP for content analysis and network monitoring for SSL-specific checks.

### Example Findings Review

```bash
python -m toonic.server.client
toonic> history 10
toonic> query "security vulnerabilities with high confidence"
toonic> query "TLS or SSL configuration issues"
toonic> query "exposed endpoints or admin interfaces"
toonic> sql SELECT target_path, content FROM exchanges WHERE action_type='alert' AND content LIKE '%security%' ORDER BY timestamp DESC
```

### Generate Markdown Report

After running the security audit, generate a comprehensive Markdown report:

```bash
# Generate report from analysis data
cd examples/security-audit
python3 generate_report.py \
  --data-dir ../../toonic_data \
  --goal "SSL/TLS security analysis of obywatel.bielik.ai" \
  --output obywatel_security_audit.md

# View the report
cat obywatel_security_audit.md
```

**Report Features:**
- Executive summary with confidence scores
- Detailed security findings
- Affected files and recommendations
- Analysis context and conversation history
- Next steps for remediation

The report script automatically:
- Filters for security-related findings
- Ranks by confidence level
- Provides actionable recommendations
- Formats output in professional Markdown

## Priority in Security Context

When combining code + logs, the Accumulator ensures:
- **CRITICAL log lines** (auth failures, crashes) → priority 1.0, always in LLM context
- **ERROR log lines** → priority 0.8
- **Code chunks** → priority 0.5 (normal)
- **INFO/DEBUG logs** → priority 0.1–0.3, evicted first

This means the LLM always sees the most security-relevant data, even under tight token budgets.
