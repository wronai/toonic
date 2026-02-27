#!/usr/bin/env bash
set -euo pipefail

exec toonic-server \
  --source "https://httpbin.org/" \
  --source "net:httpbin.org" \
  --goal "web security audit: OWASP Top 10, security headers, TLS config" \
  --interval 60
