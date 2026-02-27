# Example: HTTP / API Endpoint Monitoring

Monitor HTTP/HTTPS endpoints for availability, response time, content changes,
SSL certificate expiry, and keyword detection.

## Quick Start (one-liner)

```python
from toonic.server.quick import run
run("https://api.example.com/health", goal="monitor API uptime and response times")
```

## Quick Start (CLI)

```bash
# Monitor a single endpoint
python -m toonic.server \
  --source https://api.example.com/health \
  --goal "monitor API: uptime, response times, content changes" \
  --interval 30

# Monitor multiple endpoints
python -m toonic.server \
  --source https://api.example.com/health \
  --source https://staging.example.com/health \
  --source https://admin.example.com/ \
  --goal "multi-endpoint monitoring: detect downtime, slow responses, SSL issues"
```

## Quick Start (Python)

```python
from toonic.server.quick import watch

server = (
    watch()
    .http("https://api.example.com/health")
    .http("https://staging.example.com/health")
    .http("https://admin.example.com/")
    .goal("API uptime monitoring: response times, status codes, SSL expiry")
    .interval(30)
    .build()
)
```

## What HttpWatcher Tracks

| Check | Description |
|-------|------------|
| **Status code** | 200, 404, 500, etc. — alerts on unexpected status |
| **Response time** | Milliseconds — detects slowdowns (>2x previous) |
| **Content hash** | SHA256 — detects content changes |
| **SSL certificate** | Days until expiry — warns at <30 days |
| **Keywords** | Checks for presence/absence of specific strings |
| **Redirects** | Tracks redirect chains |
| **Connection errors** | Timeouts, DNS failures, refused connections |

## HttpWatcher Options

| Option | Default | Description |
|--------|---------|------------|
| `poll_interval` | 30.0 | Seconds between checks |
| `timeout` | 10.0 | Request timeout in seconds |
| `method` | GET | HTTP method (GET, POST, HEAD, etc.) |
| `expected_status` | 200 | Expected status code (alerts on mismatch) |
| `keywords` | [] | Keywords to check in response body |
| `check_ssl` | true | Check SSL certificate expiry |
| `follow_redirects` | true | Follow HTTP redirects |
| `content_hash_only` | false | Only track content hash, not full body |

## Advanced: with options

```python
from toonic.server.quick import watch

server = (
    watch()
    .add("https://api.example.com/health",
         poll_interval=15,
         expected_status=200,
         timeout=5)
    .add("https://api.example.com/v2/status",
         method="POST",
         expected_status=200)
    .goal("API health monitoring with custom checks")
    .build()
)
```

## Combined with other sources

```bash
# API + logs + network — full service monitoring
python -m toonic.server \
  --source https://api.example.com/health \
  --source log:./logs/api.log \
  --source "net:api.example.com,db.example.com" \
  --source port:5432 \
  --goal "service health: API uptime + log errors + network + database"
```

```python
from toonic.server.quick import watch

server = (
    watch()
    .http("https://api.example.com/health")
    .logs("./logs/api.log")
    .network("api.example.com,db.example.com")
    .process("port:5432")
    .goal("full service health monitoring")
    .interval(30)
    .build()
)
```
