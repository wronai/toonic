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

## What It Does

1. Reads last 100 lines on startup (full TOON spec)
2. Tails for new lines every 2 seconds
3. Categorizes: ERROR, WARNING, INFO
4. Sends log context to LLM for analysis
5. LLM detects patterns and suggests fixes
