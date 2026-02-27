# Example: Protocol Recipes (Quick API + CLI)

This example collects ready-to-run command recipes for multiple source protocols.

## Python Quick API (recommended)

### 1) HTTP + network + process checks

```python
from toonic.server.quick import run

run(
    "https://httpbin.org/get",
    "net:8.8.8.8,1.1.1.1",
    "proc:nginx",
    goal="api uptime + network + process health",
    interval=30,
)
```

### 2) RTSP video + logs

```python
from toonic.server.quick import run

run(
    "rtsp://localhost:8554/test-cam1",
    "log:./docker/test-data/sample.logfile",
    goal="detect camera events and correlate with logs",
    interval=10,
)
```

### 3) Database DSNs (protocol URLs)

```python
from toonic.server.quick import watch

server = (
    watch(
        "postgresql://user:pass@db:5432/app",
        "mysql://user:pass@db:3306/app",
        "redis://cache:6379",
        "mongodb://mongo:27017/app",
    )
    .goal("database connectivity and schema health")
    .interval(60)
    .build()
)
```

### 4) Archive + directory

```python
from toonic.server.quick import watch_archive

server = (
    watch_archive("./bundle.zip", include_files_as_sources=True)
    .goal("analyze extracted archive + monitor changes")
    .interval(0)
    .build()
)
```

## CLI Recipes

### 1) HTTP endpoint monitor

```bash
python -m toonic.server \
  --source "https://httpbin.org/get" \
  --goal "api health and response drift" \
  --interval 30
```

### 2) RTSP stream monitor

```bash
python -m toonic.server \
  --source "rtsp://localhost:8554/test-cam1" \
  --goal "cctv event monitoring" \
  --interval 10
```

### 3) Database URL monitor

```bash
python -m toonic.server \
  --source "postgresql://user:pass@db:5432/app" \
  --goal "database availability and changes" \
  --interval 60
```

### 4) Mixed watcher prefixes

```bash
python -m toonic.server \
  --source "docker:*" \
  --source "net:8.8.8.8" \
  --source "proc:nginx" \
  --goal "infra health across container/network/process" \
  --interval 30
```

## Unsupported CLI protocol examples (expected fail-fast)

These protocols are intentionally rejected by CLI parser (`parse_source_string`):

```bash
python -m toonic.server --source "mqtt://broker:1883/topic" --goal "test"
python -m toonic.server --source "amqp://mq" --goal "test"
```

Use supported protocols (`http(s)`, `ws(s)`, `grpc`, `rtsp`, DB URLs) or watcher prefixes (`net:`, `proc:`, `docker:`, `dir:`, `log:`).
