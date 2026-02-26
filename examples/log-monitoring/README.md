# Example: Log Monitoring

Monitor application logs in real-time and detect anomalies.

## Quick Start

```bash
# Start server monitoring a log file
python -m toonic.server \
  --source log:./docker/test-data/sample.logfile \
  --goal "monitor logs, detect errors, and suggest fixes" \
  --interval 10

# Open http://localhost:8900 for live event stream
```

## Simulating Log Activity

```bash
# In another terminal, append log lines to trigger delta analysis
echo "2026-02-26 12:00:00 ERROR [api] NullPointerException in UserController.getProfile()" \
  >> ./docker/test-data/sample.logfile

echo "2026-02-26 12:00:01 CRITICAL [db] Connection pool exhausted — 0/100 available" \
  >> ./docker/test-data/sample.logfile
```

## Event-Driven with Triggers

```bash
# Trigger on error patterns (5 errors in 60s)
python -m toonic.server \
  --source log:./docker/test-data/sample.logfile \
  --goal "analyze error spike and suggest fixes" \
  --when "when error occurs 5 times in 60 seconds"

# This generates triggers.yaml:
triggers:
  - name: error-spike
    mode: on_event
    source: logs
    events:
      - type: pattern
        regex: "ERROR|CRITICAL"
        count_threshold: 5
        window_s: 60
    fallback:
      periodic_s: 120
    goal: "analyze error spike and suggest fixes"
```

## What It Does

1. Reads last 100 lines on startup (full TOON spec)
2. Tails for new lines every 2 seconds
3. Categorizes: ERROR, WARNING, INFO
4. **With triggers**: Only sends to LLM when error pattern detected
5. LLM detects patterns and suggests fixes
