#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "dir:${ROOT_DIR}/examples" \
  --goal "directory monitoring: detect new/deleted/modified files" \
  --interval 15
