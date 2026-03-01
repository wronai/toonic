"""
Source string parsing utilities.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Union

from toonic.server.config import SourceConfig

logger = logging.getLogger("toonic.quick.parsing")

# ══════════════════════════════════════════════════════════════
# Source string → SourceConfig parser
# ══════════════════════════════════════════════════════════════

_PREFIX_CATEGORY = {
    # Code / files
    "file": "code", "code": "code", "src": "code",
    # Logs
    "log": "logs", "logs": "logs",
    # Config
    "config": "config", "cfg": "config",
    # Data / archives
    "data": "data", "csv": "data", "json": "data", "archive": "data",
    # Documents
    "doc": "document", "document": "document", "pdf": "document",
    # Video / audio
    "video": "video", "cam": "video",
    "audio": "audio", "mic": "audio",
    # Containers
    "docker": "container", "container": "container",
    # Databases
    "db": "database", "sqlite": "database", "postgres": "database",
    "postgresql": "database", "mysql": "database", "redis": "database",
    "mongodb": "database", "mongo": "database",
    # Network
    "net": "network", "ping": "network", "dns": "network",
    # Process
    "proc": "process", "pid": "process", "port": "process",
    "tcp": "process", "service": "process",
    # Web / API
    "http": "web", "https": "web", "api": "api", "web": "web",
    "ws": "api", "wss": "api", "grpc": "api",
    # Infrastructure
    "dir": "infra", "directory": "infra",
    # Messaging (IoT / queues)
    "mqtt": "data", "amqp": "data", "kafka": "data",
    "nats": "data", "stomp": "data",
    # Remote access
    "ssh": "infra", "ftp": "data", "sftp": "data", "ldap": "network",
}

# 20 popular protocols — mapped to SourceCategory values.
_PROTO_CATEGORY = {
    # Web / HTTP  →  HttpWatcher
    "http": "web", "https": "web",
    # WebSocket   →  HttpWatcher (HTTP upgrade probe)
    "ws": "api", "wss": "api",
    # gRPC          →  HttpWatcher (HTTP/2-based)
    "grpc": "api",
    # Video streaming  →  StreamWatcher
    "rtsp": "video", "rtsps": "video", "rtmp": "video",
    # Databases  →  DatabaseWatcher
    "postgresql": "database", "postgres": "database",
    "mysql": "database", "redis": "database", "mongodb": "database",
    # File transfer (no watcher yet)
    "ftp": "data", "sftp": "data",
    # SSH (no watcher yet)
    "ssh": "infra",
    # Messaging / IoT (no watcher yet)
    "mqtt": "data", "amqp": "data", "kafka": "data", "nats": "data",
    # Bonus
    "ldap": "network", "stomp": "data",
}


_EXT_MAP = {
    ".log": "logs", ".logs": "logs",
    ".db": "database", ".sqlite": "database", ".sqlite3": "database",
    ".csv": "data", ".tsv": "data", ".parquet": "data",
    ".json": "data", ".jsonl": "data", ".ndjson": "data",
    ".yaml": "config", ".yml": "config", ".toml": "config", ".ini": "config", ".env": "config",
    ".md": "document", ".rst": "document", ".txt": "document", ".pdf": "document",
    ".mp4": "video", ".avi": "video", ".mkv": "video", ".mov": "video",
    ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".ogg": "audio",
    ".zip": "data", ".tar": "data",
}


_ARCHIVE_SUFFIXES = (".tar", ".gz"), (".tar", ".bz2"), (".tar", ".xz")


def _is_archive_suffix(suffixes: list) -> bool:
    """Check if path suffixes indicate an archive file."""
    return len(suffixes) >= 2 and tuple(suffixes[-2:]) in _ARCHIVE_SUFFIXES


def _detect_category_from_path(source_str: str) -> str:
    """Auto-detect category from file path extension/name."""
    p = Path(source_str)
    ext = p.suffix.lower()
    suffixes = [s.lower() for s in p.suffixes]
    name = p.name.lower()

    if _is_archive_suffix(suffixes):
        return "data"

    if ext in _EXT_MAP:
        return _EXT_MAP[ext]

    if "log" in name:
        return "logs"

    if p.is_dir() or (not p.suffix and not p.exists()):
        return "code"

    return "code"


def _parse_protocol_url(source_str: str) -> SourceConfig | None:
    """Parse protocol URLs (rtsp://, http://, etc.). Returns None if not a protocol URL."""
    if "://" not in source_str or source_str.startswith("file:"):
        return None

    proto = source_str.split("://")[0].lower()
    cat = _PROTO_CATEGORY.get(proto, "data")
    return SourceConfig(path_or_url=source_str, category=cat)


def _parse_prefixed_source(source_str: str) -> SourceConfig | None:
    """Parse prefixed sources (log:./app.log, docker:*). Returns None if no prefix."""
    if ":" not in source_str:
        return None

    prefix, _, _path = source_str.partition(":")
    cat = _PREFIX_CATEGORY.get(prefix.lower(), "code")
    return SourceConfig(path_or_url=source_str, category=cat)


def parse_source(source: Union[str, SourceConfig, Dict[str, Any]]) -> SourceConfig:
    """Parse any source specification into SourceConfig.

    Accepts:
        - SourceConfig object (passthrough)
        - Dict with path_or_url + optional category/options
        - String: "prefix:path", "proto://url", or plain path
    """
    if isinstance(source, SourceConfig):
        return source

    if isinstance(source, dict):
        return SourceConfig(**{k: v for k, v in source.items() if hasattr(SourceConfig, k)})

    source_str = str(source).strip()

    # Protocol URL
    if result := _parse_protocol_url(source_str):
        return result

    # Prefixed source
    if result := _parse_prefixed_source(source_str):
        return result

    # Plain path — auto-detect from extension / content
    cat = _detect_category_from_path(source_str)
    return SourceConfig(path_or_url=source_str, category=cat)
