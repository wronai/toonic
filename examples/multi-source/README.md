# Example: Multi-Source Monitoring

Combine code, logs, video streams, databases, and network checks in a single
priority-aware analysis context — showcasing the LLM Pipeline, priority-based
Accumulator, and multi-trigger scheduling.

## Architecture

```
┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐
│ FileWatcher  │  │ LogWatcher   │  │ StreamWatcher│  │ DatabaseWatch│  │ NetworkWatch│
│ (code)       │  │ (logs)       │  │ (video/RTSP) │  │ (SQLite/PG)  │  │ (ping/DNS)  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘
       │ chunks          │ chunks          │ chunks          │ chunks          │ chunks
       │ pri=0.5         │ pri=0.3–1.0     │ pri=0.2–0.9    │ pri=0.5         │ pri=0.5
       ▼                 ▼                 ▼                 ▼                 ▼
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                     ContextAccumulator (priority-based eviction)                  │
  │  token_allocation: code=25%, logs=20%, video=20%, db=5%, net=5%, system=10%      │
  │  get_chunks() → highest-priority chunks per category within budget               │
  └─────────────────────────────────┬────────────────────────────────────────────────┘
                                    │ (chunks, images)
                                    ▼
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                     TriggerScheduler (multi-rule evaluation)                      │
  │  cctv-intrusion (on_event) │ error-spike (on_event) │ code-review (periodic)     │
  └─────────────────────────────────┬────────────────────────────────────────────────┘
                                    │ trigger fires
                                    ▼
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                     LLMPipeline (prompt → model → call → parse)                  │
  │  auto-selects: GenericPrompt │ CodeAnalysisPrompt │ CCTVEventPrompt              │
  └─────────────────────────────────┬────────────────────────────────────────────────┘
                                    │ ActionResponse
                                    ▼
  ┌───────────────────────────────────────────────────────────┐
  │  Web UI (http://localhost:8900)  │  REST API  │  WebSocket │
  └───────────────────────────────────────────────────────────┘
```

---

## Quick Start (with YAML config)

```bash
# Start with the included multi-source config
python -m toonic.server --config examples/multi-source/toonic-server.yaml

# Open http://localhost:8900 for full Web UI
```

## Quick Start (CLI flags)

```bash
# Start server with multiple sources + triggers
python -m toonic.server \
  --source file:./examples/code-analysis/sample-project/ \
  --source log:./docker/test-data/sample.logfile \
  --source rtsp://localhost:8554/test-cam1 \
  --goal "comprehensive analysis: code quality + log anomalies + video monitoring" \
  --triggers examples/multi-source/example-triggers.yaml \
  --interval 30

# Open http://localhost:8900
```

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

---

## Priority-Based Context Management

Each watcher assigns **priority** (0.0–1.0) and **content_type** to emitted chunks.
The Accumulator uses these to decide what to keep when the token budget is full:

| Source | ContentType | Priority | Eviction behavior |
|--------|------------|----------|-------------------|
| LogWatcher (CRITICAL) | `LOG_ENTRIES` | **1.0** | Never evicted first |
| LogWatcher (ERROR) | `LOG_ENTRIES` | **0.8** | High retention |
| StreamWatcher (detection) | `VIDEO_EVENT` | **0.9** | High retention |
| StreamWatcher (heartbeat) | `VIDEO_HEARTBEAT` | **0.2** | Evicted early |
| LogWatcher (WARNING) | `LOG_ENTRIES` | **0.5** | Normal |
| LogWatcher (INFO) | `LOG_ENTRIES` | **0.3** | Low retention |
| FileWatcher | `TOON_SPEC` | **0.5** | Normal |
| DatabaseWatcher | `SCHEMA_DIFF` | **0.5** | Normal |
| NetworkWatcher | `HTTP_STATUS` | **0.5** | Normal |

When the token budget fills up, the Accumulator evicts **lowest-priority + oldest**
chunks first, ensuring critical events are always included in LLM context.

---

## Multi-Trigger Scheduling

The `example-triggers.yaml` defines 5 independent trigger rules:

| Rule | Mode | Source | When it fires |
|------|------|--------|---------------|
| `cctv-intrusion` | on_event | video | Person/car detected for ≥1s |
| `error-spike` | on_event | logs | ≥3 ERROR/CRITICAL in 60s |
| `code-review` | periodic | code | Every 5 minutes |
| `network-alert` | on_event | network | Connectivity anomaly |
| `db-watch` | on_event | database | Schema or row count change |

Each rule has its own **goal override**, **priority**, and **fallback** behavior.
The TriggerScheduler evaluates all rules independently — multiple can fire simultaneously.

---

## Adding Sources Dynamically

Via Web UI (http://localhost:8900):
- Use the "Sources" panel to add new sources at runtime

Via CLI Shell:
```bash
python -m toonic.server.client
toonic> add ./new-project/ code
toonic> add ./logs/error.log logs
toonic> add rtsp://192.168.1.50:554/stream video
toonic> add docker:* container
toonic> add db:./app.db database
toonic> add net:google.com,cloudflare.com network
toonic> add proc:nginx process
toonic> analyze what changed since last analysis?
```

Via API:
```bash
# Add a database source
curl -X POST http://localhost:8900/api/sources \
  -H "Content-Type: application/json" \
  -d '{"path_or_url": "db:./app.db", "category": "database"}'

# Add a network monitor
curl -X POST http://localhost:8900/api/sources \
  -H "Content-Type: application/json" \
  -d '{"path_or_url": "net:8.8.8.8,1.1.1.1", "category": "network"}'

# Add Docker container monitoring
curl -X POST http://localhost:8900/api/sources \
  -H "Content-Type: application/json" \
  -d '{"path_or_url": "docker:*", "category": "container"}'
```

---

## RTSP Streams (Docker)

The Docker setup provides test streams:
- `rtsp://localhost:8554/test-cam1` — 640x480 test pattern + 440Hz tone
- `rtsp://localhost:8554/test-cam2` — 320x240 SMPTE bars + 880Hz tone
- `rtsp://localhost:8554/test-audio` — Audio-only 300Hz sine wave

---

## Querying Across Sources

```bash
python -m toonic.server.client
toonic> history 20
toonic> query "all critical findings across code and logs"
toonic> query "video events with high confidence"
toonic> sql SELECT action_type, COUNT(*) FROM exchanges GROUP BY action_type
toonic> sql SELECT category, content FROM exchanges WHERE confidence > 0.8 ORDER BY timestamp DESC LIMIT 10
```

---

## Files in This Example

- **`README.md`** — this file
- **`toonic-server.yaml`** — full server config with 5 source types + token allocation
- **`example-triggers.yaml`** — multi-rule trigger config (copy to `triggers.yaml` to use)
