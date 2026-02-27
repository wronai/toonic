#!/usr/bin/env bash
set -euo pipefail

exec toonic-server \
  --source "rtsp://localhost:8554/test-cam1" \
  --goal "describe video frames, caption each scene change" \
  --interval 10
