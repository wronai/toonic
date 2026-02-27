# Example: Log Monitoring with Priority

Monitor application logs in real-time with **priority-aware context management**
and **multi-rule trigger scheduling**.

## How Priority Works

LogWatcher assigns priority based on log severity:

| Log Level | Priority | ContentType | Accumulator behavior |
|-----------|----------|-------------|---------------------|
| CRITICAL / FATAL | **1.0** | `LOG_ENTRIES` | Never evicted first |
| ERROR | **0.8** | `LOG_ENTRIES` | High retention |
| WARNING | **0.5** | `LOG_ENTRIES` | Normal retention |
| INFO | **0.3** | `LOG_ENTRIES` | Low retention |
| DEBUG / TRACE | **0.1** | `LOG_ENTRIES` | Evicted early |

When the token budget fills up, low-priority INFO/DEBUG lines are evicted first,
ensuring ERROR and CRITICAL lines always reach the LLM.

---

## Quick Start (Python — 1 line)

```python
from toonic.server.quick import run
run("log:./app.log", goal="monitor logs, detect errors, suggest fixes", interval=10)
```

## Quick Start (fluent builder)

```python
from toonic.server.quick import watch

server = (
    watch()
    .logs("./docker/test-data/sample.logfile")
    .goal("monitor logs, detect errors, suggest fixes")
    .triggers("examples/log-monitoring/example-triggers.yaml")
    .interval(10)
    .build()
)
```

## Quick Start (CLI)

```bash
python -m toonic.server \
  --source log:./docker/test-data/sample.logfile \
  --goal "monitor logs, detect errors, and suggest fixes" \
  --interval 10
```

## Simulating Log Activity

Use the included log generator to produce realistic test data:

```bash
# Generate mixed logs (INFO + periodic error bursts) for 2 minutes
python examples/log-monitoring/generate_logs.py \
  --output ./test-app.log \
  --mode mixed \
  --duration 120

# In another terminal, monitor the generated logs
python -m toonic.server \
  --source log:./test-app.log \
  --goal "monitor logs, detect error patterns, suggest fixes" \
  --triggers examples/log-monitoring/example-triggers.yaml
```

Or append lines manually:

```bash
echo "2026-02-26 12:00:00 ERROR [api] NullPointerException in UserController.getProfile()" \
  >> ./docker/test-data/sample.logfile

echo "2026-02-26 12:00:01 CRITICAL [db] Connection pool exhausted — 0/100 available" \
  >> ./docker/test-data/sample.logfile
```

### Log Generator Modes

| Mode | What it generates |
|------|-------------------|
| `normal` | Mostly INFO/DEBUG with occasional WARNING |
| `error-spike` | Warm-up → 10 ERROR/CRITICAL in 5s → cooldown |
| `mixed` | Realistic traffic: steady INFO, periodic error bursts |

---

## Event-Driven with Triggers

### Using `--when` (NLP → YAML)

```bash
# Natural language trigger — auto-generates triggers.yaml
python -m toonic.server \
  --source log:./docker/test-data/sample.logfile \
  --goal "analyze error spike and suggest fixes" \
  --when "when error occurs 5 times in 60 seconds"
```

### Using YAML trigger rules

```bash
# Use the included multi-rule trigger config
python -m toonic.server \
  --source log:./docker/test-data/sample.logfile \
  --triggers examples/log-monitoring/example-triggers.yaml
```

The `example-triggers.yaml` defines 4 rules:

| Rule | Mode | When it fires | Priority |
|------|------|---------------|----------|
| `critical-immediate` | on_event | Any CRITICAL/FATAL line | **10** |
| `error-spike` | on_event | ≥5 ERROR in 60s | **9** |
| `warning-trend` | on_event | ≥20 WARNING in 5min | **6** |
| `log-summary` | periodic | Every 10 minutes | **3** |

---

## What It Does

1. **Startup**: reads last 100 lines (full TOON spec with file metadata)
2. **Tailing**: polls for new lines every 2 seconds (delta TOON)
3. **Priority**: assigns priority 0.1–1.0 based on log severity
4. **ContentType**: tags all chunks as `LOG_ENTRIES`
5. **Triggers**: evaluates rules against each new chunk
6. **LLM**: receives priority-sorted context — critical errors first
7. **History**: all exchanges stored in `toonic_data/history.db`

---

## Querying Log History

```bash
python -m toonic.server.client
toonic> history 20
toonic> query "error patterns in the last hour"
toonic> query "which component has the most errors?"
toonic> sql SELECT content FROM exchanges WHERE action_type='alert' ORDER BY timestamp DESC LIMIT 5
toonic> sql SELECT category, COUNT(*) as cnt FROM exchanges GROUP BY category
```

---

## Files in This Example

- **`README.md`** — this file
- **`generate_logs.py`** — log generator script (3 modes: normal, error-spike, mixed)
- **`example-triggers.yaml`** — multi-rule trigger config with 4 rules
