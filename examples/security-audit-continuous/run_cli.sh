#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "${ROOT_DIR}/examples/code-analysis/sample-project/" \
  --source "log:${ROOT_DIR}/docker/test-data/sample.logfile" \
  --goal "continuous security monitoring: suspicious log patterns, unauthorized access attempts" \
  --interval 300
