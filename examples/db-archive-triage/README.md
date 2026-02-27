# Example: DB + Archive Triage

Combine database DSNs with archive extraction for incident triage.

## Python Quick API

```python
from toonic.server.quick import watch, watch_archive

server = (
    watch(
        "postgresql://user:pass@db:5432/app",
        "redis://cache:6379",
    )
    .dir(watch_archive("./incident-bundle.tar.gz").build_config().sources[0].path_or_url)
    .goal("triage db health and incident archive content")
    .interval(60)
    .build()
)
```

## Simpler pattern

```python
from toonic.server.quick import watch_archive

watch_archive("./incident-bundle.zip", include_files_as_sources=True) \
    .goal("inspect incident bundle and extracted files") \
    .interval(0) \
    .run()
```

## CLI

```bash
python -m toonic.server \
  --source "postgresql://user:pass@db:5432/app" \
  --source "redis://cache:6379" \
  --goal "database health triage" \
  --interval 60
```

```bash
# archive path: unpack first, then monitor directory
mkdir -p /tmp/incident && tar -xzf incident-bundle.tar.gz -C /tmp/incident
python -m toonic.server --source "dir:/tmp/incident" --goal "archive triage" --interval 0
```
