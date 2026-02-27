#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "${ROOT_DIR}/examples/code-analysis/sample-project/" \
  --goal "security audit: hardcoded secrets, injections, OWASP Top 10" \
  --interval 0
