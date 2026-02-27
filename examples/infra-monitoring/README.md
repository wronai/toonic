# Example: Infrastructure Monitoring (Docker + Database + Network)

Monitor Docker containers, databases, and network endpoints in a single
Toonic server — with priority-based context and event-driven triggers.

## Supported Watchers

| Watcher | Source prefix | What it monitors |
|---------|--------------|------------------|
| **DockerWatcher** | `docker:` | Container status, resource usage, logs, health |
| **DatabaseWatcher** | `db:` / `sqlite:` | Schema changes, row counts, query diffs |
| **NetworkWatcher** | `net:` / `ping:` / `dns:` | Connectivity, latency, DNS resolution |
| **ProcessWatcher** | `proc:` / `port:` / `pid:` | Process health, port checks, CPU/memory |

---

## Quick Start (Python — 1 line)

```python
from toonic.server.quick import run
run("docker:*", "db:./app.db", "net:8.8.8.8", "proc:nginx",
    goal="infrastructure health: containers + database + network + services")
```

## Quick Start (fluent builder)

```python
from toonic.server.quick import watch

server = (
    watch()
    .docker("*")
    .database("db:./toonic_data/history.db")
    .network("8.8.8.8,1.1.1.1,cloudflare.com")
    .process("proc:nginx")
    .process("port:5432")
    .logs("./logs/app.log")
    .goal("infrastructure health monitoring")
    .triggers("examples/infra-monitoring/example-triggers.yaml")
    .interval(15)
    .build()
)
```

## Quick Start — Docker Monitoring

```bash
python -m toonic.server \
  --source docker:* \
  --goal "monitor Docker containers: health, resource usage, restarts, errors" \
  --interval 15

# Monitor specific container
python -m toonic.server \
  --source docker:my-app \
  --goal "monitor my-app container health and logs" \
  --interval 10
```

### DockerWatcher Options

| Option | Default | Description |
|--------|---------|------------|
| `poll_interval` | 15.0 | Seconds between checks |
| `track_stats` | true | Collect CPU/memory stats |
| `track_logs` | false | Collect recent container logs |
| `log_tail` | 20 | Number of log lines to tail |

---

## Quick Start — Database Monitoring

```bash
# Monitor SQLite database
python -m toonic.server \
  --source db:./app.db \
  --goal "monitor database: schema changes, row count anomalies, growth trends" \
  --interval 30

# Monitor PostgreSQL
python -m toonic.server \
  --source db:postgresql://user:pass@localhost:5432/mydb \
  --goal "database monitoring: schema drift, table growth, connection pool" \
  --interval 30
```

### DatabaseWatcher Options

| Option | Default | Description |
|--------|---------|------------|
| `poll_interval` | 30.0 | Seconds between checks |
| `track_schema` | true | Detect schema changes (new/dropped tables, columns) |
| `track_row_counts` | true | Detect row count changes |
| `timeout` | 10.0 | Connection timeout |
| `queries` | [] | Custom SQL queries to monitor |

### Supported Databases

| Type | DSN format |
|------|-----------|
| SQLite | `db:./path/to/file.db` or `sqlite:./file.sqlite` |
| PostgreSQL | `db:postgresql://user:pass@host:5432/dbname` |

---

## Quick Start — Network Monitoring

```bash
# Monitor multiple endpoints
python -m toonic.server \
  --source "net:8.8.8.8,1.1.1.1,cloudflare.com" \
  --goal "network monitoring: connectivity, latency, DNS resolution" \
  --interval 15

# Monitor with port checks
python -m toonic.server \
  --source "net:api.example.com,db.example.com" \
  --goal "service connectivity: check all endpoints reachable" \
  --interval 10
```

### NetworkWatcher Options

| Option | Default | Description |
|--------|---------|------------|
| `poll_interval` | 15.0 | Seconds between checks |
| `timeout` | 5.0 | Connection timeout |
| `ping_count` | 3 | Number of ping attempts |
| `ports` | "" | Comma-separated ports to check |
| `check_dns` | true | Perform DNS resolution |
| `check_ping` | true | Perform ping check |

---

## Quick Start — Process / Service Monitoring

```bash
# Monitor a process by name
python -m toonic.server \
  --source proc:nginx \
  --goal "monitor nginx: running status, CPU, memory, restarts" \
  --interval 10

# Monitor a TCP port
python -m toonic.server \
  --source port:5432 \
  --goal "monitor PostgreSQL port availability and response time" \
  --interval 10

# Monitor a process by PID
python -m toonic.server \
  --source pid:1234 \
  --goal "track process resource usage and health" \
  --interval 5
```

### ProcessWatcher Target Formats

| Format | Example | What it checks |
|--------|---------|---------------|
| `proc:name` | `proc:nginx` | Process running by name |
| `pid:N` | `pid:1234` | Process by PID |
| `port:N` | `port:8080` | TCP port availability |
| `tcp:host:port` | `tcp:db:5432` | Remote TCP connectivity |
| `service:name` | `service:postgresql` | Systemd service status |

---

## Combined Infrastructure Monitoring

```bash
# Monitor everything: Docker + DB + Network + Processes
python -m toonic.server \
  --source docker:* \
  --source db:./toonic_data/history.db \
  --source "net:8.8.8.8,1.1.1.1" \
  --source proc:nginx \
  --source port:5432 \
  --goal "infrastructure health: containers, database, network, services" \
  --triggers examples/infra-monitoring/example-triggers.yaml \
  --interval 30
```

Or use the YAML config:

```bash
python -m toonic.server --config examples/infra-monitoring/toonic-server.yaml
```

---

## Querying Infrastructure History

```bash
python -m toonic.server.client
toonic> history 20
toonic> query "container restarts in the last hour"
toonic> query "network latency issues"
toonic> query "database schema changes"
toonic> sql SELECT category, action_type, content FROM exchanges ORDER BY timestamp DESC LIMIT 10
```

---

## Files in This Example

- **`README.md`** — this file
- **`toonic-server.yaml`** — combined infra monitoring config
- **`example-triggers.yaml`** — event-driven trigger rules for infra alerts
