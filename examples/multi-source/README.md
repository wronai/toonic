# Example: Multi-Source Analysis

Combine code, logs, and video streams in a single analysis context.

## Quick Start (with Docker)

```bash
# Start RTSP test streams + Toonic Server
cd docker/
docker compose up -d

# Open http://localhost:8900 for full Web UI
# - See live video keyframe events from RTSP
# - See log monitoring events
# - See code analysis results
# - Trigger manual analysis with different goals
```

## Quick Start (without Docker)

```bash
# Start server with multiple sources
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --source log:./docker/test-data/sample.logfile \
  --source rtsp://localhost:8554/test-cam1 \
  --goal "comprehensive analysis: code quality + log anomalies + video monitoring" \
  --interval 30

# Open http://localhost:8900
```

## Adding Sources Dynamically

Via Web UI (http://localhost:8900):
- Use the "Sources" panel to add new sources at runtime

Via CLI Shell:
```bash
python -m toonic.server.client
toonic> add ./new-project/ code
toonic> add ./logs/error.log logs
toonic> add rtsp://192.168.1.50:554/stream video
toonic> analyze what changed since last analysis?
```

Via API:
```bash
curl -X POST http://localhost:8900/api/sources \
  -H "Content-Type: application/json" \
  -d '{"path_or_url": "./data/metrics.csv", "category": "data"}'
```

## RTSP Streams (Docker)

The Docker setup provides test streams:
- `rtsp://localhost:8554/test-cam1` — 640x480 test pattern + 440Hz tone
- `rtsp://localhost:8554/test-cam2` — 320x240 SMPTE bars + 880Hz tone
- `rtsp://localhost:8554/test-audio` — Audio-only 300Hz sine wave
