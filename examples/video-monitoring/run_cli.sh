#!/usr/bin/env bash
set -euo pipefail

exec toonic-server \
  --source "rtsp://localhost:8554/test-cam1" \
  --goal "CCTV security: detect intrusions, describe actions, classify suspicious events" \
  --interval 0
