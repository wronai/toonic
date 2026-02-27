#!/usr/bin/env bash
set -euo pipefail

echo "Archive monitoring CLI: unpack the archive first, then run toonic-server on extracted dir" >&2
echo "Example:" >&2
echo "  unzip -q bundle.zip -d /tmp/bundle" >&2
echo "  toonic-server --source dir:/tmp/bundle --goal 'security audit of extracted archive' --interval 0" >&2
exit 2
