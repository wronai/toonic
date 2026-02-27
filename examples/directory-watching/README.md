# Example: Directory Structure Watching

Monitor directory trees for structural changes: new files, deletions, renames,
size changes, and permission modifications.

Unlike `FileWatcher` (which reads file contents for TOON conversion),
`DirectoryWatcher` focuses on **metadata and structure** — ideal for
deployment monitoring, data pipeline directories, and asset tracking.

## Quick Start (one-liner)

```python
from toonic.server.quick import run
run("dir:./deploy/", goal="monitor deployment directory for changes")
```

## Quick Start (CLI)

```bash
# Watch a deployment directory
python -m toonic.server \
  --source dir:./deploy/ \
  --goal "deployment monitoring: detect new/deleted/modified files" \
  --interval 15

# Watch multiple directories
python -m toonic.server \
  --source dir:./uploads/ \
  --source dir:./data/pipeline/ \
  --source dir:./backups/ \
  --goal "directory monitoring: uploads, data pipeline, and backups"
```

## Quick Start (Python)

```python
from toonic.server.quick import watch

server = (
    watch()
    .directory("./deploy/")
    .directory("./uploads/")
    .directory("./data/pipeline/")
    .goal("monitor directories for structural changes")
    .interval(10)
    .build()
)
```

## What DirectoryWatcher Tracks

| Change | Description |
|--------|------------|
| **New files** | Files/directories created since last scan |
| **Deleted files** | Files/directories removed since last scan |
| **Modified files** | Size or modification time changed |
| **Permission changes** | Unix permission bits changed (optional) |
| **Directory tree** | Full structure snapshot in TOON format |

## DirectoryWatcher Options

| Option | Default | Description |
|--------|---------|------------|
| `poll_interval` | 5.0 | Seconds between scans |
| `recursive` | true | Scan subdirectories |
| `max_depth` | 10 | Maximum recursion depth |
| `include_hidden` | false | Include hidden files (dotfiles) |
| `track_sizes` | true | Track file sizes |
| `track_permissions` | false | Track Unix permission changes |
| `ignore_patterns` | `.git,__pycache__,...` | Directories to ignore |

## Advanced: with options

```python
from toonic.server.quick import watch

server = (
    watch()
    .add("dir:./deploy/",
         poll_interval=5,
         recursive="true",
         track_permissions="true",
         max_depth=5)
    .add("dir:./uploads/",
         poll_interval=10,
         include_hidden="false",
         ignore_patterns=".tmp,.partial")
    .goal("deployment + upload monitoring")
    .build()
)
```

## Combined: deploy monitoring stack

```python
from toonic.server.quick import watch

server = (
    watch()
    .directory("./deploy/")
    .logs("./logs/deploy.log")
    .docker("my-app")
    .network("api.example.com")
    .process("proc:nginx")
    .goal("full deployment monitoring: files + logs + containers + services")
    .interval(10)
    .build()
)
```
