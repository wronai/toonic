#!/usr/bin/env bash
set -euo pipefail

exec toonic-server \
  --source "docker:*" \
  --source "net:8.8.8.8,1.1.1.1" \
  --goal "infrastructure health: container status, network connectivity, service availability" \
  --interval 30
