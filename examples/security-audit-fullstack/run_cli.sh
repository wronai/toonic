#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "${ROOT_DIR}/examples/code-analysis/sample-project/" \
  --source "log:${ROOT_DIR}/docker/test-data/sample.logfile" \
  --source "net:api.example.com" \
  --source "db:./app.db" \
  --source "port:5432" \
  --goal "comprehensive security audit: code + logs + exposed services + database" \
  --interval 30
