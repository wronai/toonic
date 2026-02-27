# Example: Multi-Format Data Monitoring

Monitor various data formats — CSV, JSON, YAML, TOML, Parquet, and more.
Toonic's `parse_source` auto-detects file type from extension and assigns
the correct category for optimal LLM analysis.

## Auto-Detection

The `quick` module detects format from file extension:

| Extension | Category | Watcher |
|-----------|----------|---------|
| `.py`, `.js`, `.rs`, `.go`, `.java`, `.ts` | `code` | FileWatcher |
| `.log`, `.logs` | `logs` | LogWatcher |
| `.csv`, `.tsv`, `.parquet`, `.jsonl`, `.ndjson` | `data` | FileWatcher |
| `.json` | `data` | FileWatcher |
| `.yaml`, `.yml`, `.toml`, `.ini`, `.env` | `config` | FileWatcher |
| `.md`, `.rst`, `.txt`, `.pdf` | `document` | FileWatcher |
| `.db`, `.sqlite`, `.sqlite3` | `database` | DatabaseWatcher |
| `.mp4`, `.avi`, `.mkv` | `video` | StreamWatcher |
| `.mp3`, `.wav`, `.flac` | `audio` | StreamWatcher |

## Archives (ZIP / TAR)

Toonic can **detect archive extensions** (e.g. `.zip`, `.tar`, `.tar.gz`) via `parse_source()`,
but **it does not unpack archives automatically** when running the server.

Use the `quick` helpers:

```python
from toonic.server.quick import unpack_archive, watch_archive

# Option A: unpack → watch directory
extracted = unpack_archive("./bundle.tar.gz")
server = watch_archive("./bundle.zip", include_files_as_sources=True)

# Or explicitly:
# server = watch(f"dir:{extracted}").goal("analyze archive contents").build()
```

## Quick Start (one-liner)

```python
from toonic.server.quick import run

# Auto-detects all types
run(
    "./src/",              # code
    "./config.yaml",       # config
    "./data/metrics.csv",  # data
    "./app.log",           # logs
    "./docs/README.md",    # document
    goal="analyze project: code + config + data + logs + docs",
)
```

## Quick Start (CLI)

```bash
# Mixed formats — Toonic auto-detects categories
python -m toonic.server \
  --source file:./src/ \
  --source config:./config.yaml \
  --source data:./metrics.csv \
  --source log:./app.log \
  --source doc:./docs/README.md \
  --goal "analyze all formats: code quality, config issues, data anomalies, log errors"
```

## Quick Start (Python)

```python
from toonic.server.quick import watch

server = (
    watch()
    .code("./src/")
    .add("./config.yaml")        # auto → config
    .add("./data/metrics.csv")   # auto → data
    .add("./data/events.jsonl")  # auto → data
    .add("./app.log")            # auto → logs
    .add("./docs/README.md")     # auto → document
    .goal("multi-format analysis")
    .interval(60)
    .build()
)
```

## Prefix-Based Source Types

For explicit control, use prefixes:

```python
from toonic.server.quick import watch

server = (
    watch()
    .add("code:./src/")           # force code category
    .add("config:./settings.ini") # force config
    .add("data:./output.json")    # force data
    .add("log:./app.log")         # force logs
    .add("doc:./report.pdf")      # force document
    .add("csv:./metrics.csv")     # data shortcut
    .add("json:./events.json")    # data shortcut
    .goal("explicitly categorized sources")
    .build()
)
```

## Protocol-Based Sources

```python
from toonic.server.quick import watch

server = (
    watch()
    .add("http://api.example.com/data.json")       # auto → api
    .add("postgresql://user:pass@db:5432/mydb")     # auto → database
    .add("rtsp://cam:554/stream")                   # auto → video
    .add("redis://cache:6379")                      # auto → database
    .goal("multi-protocol monitoring")
    .build()
)
```

## TOON Format Output

Each file format is converted to compact TOON notation before sending to the LLM.
This reduces token usage by 60–90% compared to raw file content:

```
# Python code → TOON
M app.py | c UserService | m get_user(id) → User | m delete_user(id) → bool

# YAML config → TOON  
C config.yaml | k:database.host=localhost | k:database.port=5432

# CSV data → TOON
D metrics.csv | rows=1000 | cols=5 | schema: timestamp,cpu,memory,disk,network

# Log file → TOON
L app.log | lines=500 | ERROR:12 WARNING:45 INFO:443
```

## Token Budget Management

When monitoring many formats, use `tokens()` to control allocation:

```python
from toonic.server.quick import watch

server = (
    watch("./src/", "./config.yaml", "./data.csv", "./app.log")
    .goal("balanced multi-format analysis")
    .tokens(100_000, {
        "code": 0.35,
        "config": 0.10,
        "data": 0.15,
        "logs": 0.20,
        "document": 0.10,
        "system": 0.10,
    })
    .build()
)
```
