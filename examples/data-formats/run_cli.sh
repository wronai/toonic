#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "file:${ROOT_DIR}/examples/code-analysis/sample-project/" \
  --source "doc:${ROOT_DIR}/README.md" \
  --goal "analyze all formats: code quality + docs" \
  --interval 0
