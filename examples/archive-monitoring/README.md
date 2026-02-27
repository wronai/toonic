# Example: Archive Monitoring (ZIP / TAR)

This example shows how to work with archives in Toonic in a **simple, programmatic** way.

Typical use-cases:

- security audit of a source code dump (`.zip`)
- monitoring backup archives (`.tar.gz`) for unexpected files
- quick triage of incident bundles (logs + configs + dumps)

## Quick Start (Python — unpack + watch)

```python
from toonic.server.quick import watch_archive

server = (
    watch_archive("./bundle.zip", include_files_as_sources=True)
    .goal("security audit: scan extracted files for secrets, insecure configs, vulnerable patterns")
    .interval(0)
    .build()
)
```

## Quick Start (Python — one-liner)

```python
from toonic.server.quick import run, unpack_archive

extracted = unpack_archive("./bundle.tar.gz")
run(f"dir:{extracted}", goal="analyze archive contents", interval=0)
```

## Quick Start (CLI)

Toonic CLI does not unpack archives automatically (by design).
Use Python helpers above, or unpack manually:

```bash
mkdir -p /tmp/bundle
unzip -q bundle.zip -d /tmp/bundle

python -m toonic.server \
  --source dir:/tmp/bundle \
  --goal "security audit of extracted archive" \
  --interval 0
```

## How it works

- **`unpack_archive(path)`**
  - extracts ZIP or TAR (including `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`)
  - uses a temp dir by default

- **`watch_archive(path, include_files_as_sources=True)`**
  - extracts the archive
  - adds `dir:<extracted_dir>` to watch directory structure changes
  - optionally adds individual files as sources so FileWatcher produces TOON specs per file

## Notes

- `include_files_as_sources=True` is best for code archives (you get TOON specs per file)
- For huge archives, leave it off and rely on directory structure snapshot + manual selection
