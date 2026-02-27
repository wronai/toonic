#!/usr/bin/env bash
set -euo pipefail

exec toonic-server \
  --source "https://httpbin.org/get" \
  --source "https://httpbin.org/status/200" \
  --goal "web monitoring: uptime, response times, SSL expiry, security headers" \
  --interval 60
