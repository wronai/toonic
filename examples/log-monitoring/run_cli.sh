#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec toonic-server \
  --source "log:${ROOT_DIR}/docker/test-data/sample.logfile" \
  --goal "log monitoring: detect error spikes, anomaly patterns, correlate failures" \
  --interval 10
