#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "${ROOT_DIR}/examples/code-analysis/sample-project/" \
  --goal "code review: find bugs, dead code, performance issues, SOLID violations" \
  --interval 0
