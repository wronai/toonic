# Example: Infra Triage (Docker + Net + Proc + Dir)

This recipe combines infra-focused sources into one triage config.

## Python Quick API

```python
from toonic.server.quick import run

run(
    "docker:*",
    "net:8.8.8.8,1.1.1.1",
    "proc:nginx",
    "port:5432",
    "dir:./examples/",
    goal="triage infra health and deployment drift",
    interval=30,
)
```

## CLI

```bash
python -m toonic.server \
  --source "docker:*" \
  --source "net:8.8.8.8,1.1.1.1" \
  --source "proc:nginx" \
  --source "port:5432" \
  --source "dir:./examples/" \
  --goal "infra triage" \
  --interval 30
```
