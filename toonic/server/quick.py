"""
Quick-start helpers — one-liner functions for common monitoring scenarios.

Usage:
    from toonic.server.quick import monitor, watch, serve

    # One-liner: monitor logs
    await monitor("log:./app.log", goal="detect errors")

    # Fluent builder
    srv = (
        watch("./src/", category="code")
        .add("log:./app.log")
        .add("docker:*")
        .add("net:8.8.8.8,1.1.1.1")
        .goal("full-stack monitoring")
        .when("error occurs 5 times in 60 seconds")
        .interval(30)
        .build()
    )
    await serve(srv)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from toonic.server.config import ModelConfig, ServerConfig, SourceConfig

logger = logging.getLogger("toonic.quick")

# ══════════════════════════════════════════════════════════════
# Source string → SourceConfig parser (improved)
# ══════════════════════════════════════════════════════════════

_PREFIX_CATEGORY = {
    "file": "code", "code": "code", "src": "code",
    "log": "logs", "logs": "logs",
    "config": "config", "cfg": "config",
    "data": "data", "csv": "data", "json": "data",
    "doc": "document", "document": "document", "pdf": "document",
    "video": "video", "cam": "video",
    "audio": "audio", "mic": "audio",
    "docker": "container", "container": "container",
    "db": "database", "sqlite": "database", "postgres": "database", "postgresql": "database", "mysql": "database",
    "net": "network", "ping": "network", "dns": "network",
    "proc": "process", "pid": "process", "port": "process", "tcp": "process", "service": "process",
    "http": "api", "https": "api", "api": "api",
    "dir": "infra", "directory": "infra",
}

_PROTO_CATEGORY = {
    "rtsp": "video", "rtsps": "video",
    "http": "api", "https": "api",
    "ws": "api", "wss": "api",
    "mqtt": "data", "amqp": "data",
    "postgresql": "database", "postgres": "database", "mysql": "database",
    "redis": "database", "mongodb": "database",
}


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

    # Protocol URL: rtsp://..., http://..., postgresql://...
    if "://" in source_str and not source_str.startswith("file:"):
        proto = source_str.split("://")[0].lower()
        cat = _PROTO_CATEGORY.get(proto, "data")
        return SourceConfig(path_or_url=source_str, category=cat)

    # Prefixed: log:./app.log, docker:*, db:./app.db
    if ":" in source_str:
        prefix, _, path = source_str.partition(":")
        cat = _PREFIX_CATEGORY.get(prefix.lower(), "code")
        return SourceConfig(path_or_url=source_str, category=cat)

    # Plain path — auto-detect from extension / content
    p = Path(source_str)
    ext = p.suffix.lower()
    name = p.name.lower()

    ext_map = {
        ".log": "logs", ".logs": "logs",
        ".db": "database", ".sqlite": "database", ".sqlite3": "database",
        ".csv": "data", ".tsv": "data", ".parquet": "data",
        ".json": "data", ".jsonl": "data", ".ndjson": "data",
        ".yaml": "config", ".yml": "config", ".toml": "config", ".ini": "config", ".env": "config",
        ".md": "document", ".rst": "document", ".txt": "document", ".pdf": "document",
        ".mp4": "video", ".avi": "video", ".mkv": "video", ".mov": "video",
        ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".ogg": "audio",
    }

    if ext in ext_map:
        cat = ext_map[ext]
    elif "log" in name:
        cat = "logs"
    elif p.is_dir() or (not p.suffix and not p.exists()):
        cat = "code"
    else:
        cat = "code"

    return SourceConfig(path_or_url=source_str, category=cat)


# ══════════════════════════════════════════════════════════════
# ConfigBuilder — fluent API
# ══════════════════════════════════════════════════════════════

class ConfigBuilder:
    """Fluent builder for ServerConfig + ToonicServer.

    Usage:
        srv = (
            watch("./src/")
            .add("log:./app.log")
            .goal("find bugs and monitor errors")
            .interval(30)
            .port(8900)
            .build()
        )
    """

    def __init__(self):
        self._sources: List[SourceConfig] = []
        self._goal: str = "analyze and monitor"
        self._interval: float = 30.0
        self._host: str = "0.0.0.0"
        self._port: int = 8900
        self._model: str = ""
        self._max_tokens: int = 100_000
        self._token_alloc: Optional[Dict[str, float]] = None
        self._when: str = ""
        self._triggers_file: str = ""
        self._log_level: str = "INFO"
        self._no_web: bool = False
        self._history: bool = True
        self._options: Dict[str, Any] = {}

    # ── Source methods ──

    def add(self, source: Union[str, SourceConfig, Dict], **options) -> ConfigBuilder:
        """Add a data source. Auto-detects category from prefix/extension."""
        src = parse_source(source)
        if options:
            src.options.update({k: str(v) for k, v in options.items()})
        self._sources.append(src)
        return self

    def code(self, path: str, **opts) -> ConfigBuilder:
        """Add code source."""
        return self.add(SourceConfig(path_or_url=path, category="code", options={k: str(v) for k, v in opts.items()}))

    def logs(self, path: str, **opts) -> ConfigBuilder:
        """Add log source."""
        return self.add(SourceConfig(path_or_url=path, category="logs", options={k: str(v) for k, v in opts.items()}))

    def video(self, url: str, **opts) -> ConfigBuilder:
        """Add video/RTSP source."""
        return self.add(SourceConfig(path_or_url=url, category="video", options={k: str(v) for k, v in opts.items()}))

    def docker(self, filter: str = "*", **opts) -> ConfigBuilder:
        """Add Docker container monitoring."""
        return self.add(SourceConfig(path_or_url=f"docker:{filter}", category="container", options={k: str(v) for k, v in opts.items()}))

    def database(self, dsn: str, **opts) -> ConfigBuilder:
        """Add database monitoring."""
        return self.add(SourceConfig(path_or_url=dsn, category="database", options={k: str(v) for k, v in opts.items()}))

    def network(self, targets: str, **opts) -> ConfigBuilder:
        """Add network monitoring (comma-separated hosts)."""
        return self.add(SourceConfig(path_or_url=f"net:{targets}", category="network", options={k: str(v) for k, v in opts.items()}))

    def process(self, target: str, **opts) -> ConfigBuilder:
        """Add process/port/service monitoring."""
        return self.add(SourceConfig(path_or_url=target, category="process", options={k: str(v) for k, v in opts.items()}))

    def http(self, url: str, **opts) -> ConfigBuilder:
        """Add HTTP API endpoint monitoring."""
        return self.add(SourceConfig(path_or_url=url, category="api", options={k: str(v) for k, v in opts.items()}))

    def directory(self, path: str, **opts) -> ConfigBuilder:
        """Add directory structure monitoring."""
        return self.add(SourceConfig(path_or_url=f"dir:{path}", category="infra", options={k: str(v) for k, v in opts.items()}))

    # ── Config methods ──

    def goal(self, goal: str) -> ConfigBuilder:
        """Set analysis goal."""
        self._goal = goal
        return self

    def interval(self, seconds: float) -> ConfigBuilder:
        """Set analysis interval (0 = one-shot)."""
        self._interval = seconds
        return self

    def model(self, model_name: str) -> ConfigBuilder:
        """Set LLM model."""
        self._model = model_name
        return self

    def port(self, port: int) -> ConfigBuilder:
        """Set HTTP port."""
        self._port = port
        return self

    def host(self, host: str) -> ConfigBuilder:
        """Set server host."""
        self._host = host
        return self

    def tokens(self, max_tokens: int, allocation: Optional[Dict[str, float]] = None) -> ConfigBuilder:
        """Set token budget and optional per-category allocation."""
        self._max_tokens = max_tokens
        if allocation:
            self._token_alloc = allocation
        return self

    def when(self, condition: str) -> ConfigBuilder:
        """Set NLP trigger condition (e.g. 'error occurs 5 times in 60s')."""
        self._when = condition
        return self

    def triggers(self, yaml_path: str) -> ConfigBuilder:
        """Load trigger rules from YAML file."""
        self._triggers_file = yaml_path
        return self

    def no_web(self) -> ConfigBuilder:
        """Disable web UI."""
        self._no_web = True
        return self

    def no_history(self) -> ConfigBuilder:
        """Disable history database."""
        self._history = False
        return self

    def log_level(self, level: str) -> ConfigBuilder:
        """Set log level (DEBUG, INFO, WARNING, ERROR)."""
        self._log_level = level
        return self

    # ── Build ──

    def build_config(self) -> ServerConfig:
        """Build ServerConfig from builder state."""
        cfg = ServerConfig.from_env()
        cfg.host = self._host
        cfg.port = self._port
        cfg.goal = self._goal
        cfg.interval = self._interval
        cfg.max_context_tokens = self._max_tokens
        cfg.log_level = self._log_level
        cfg.history_enabled = self._history
        if self._token_alloc:
            cfg.token_allocation = self._token_alloc
        if self._model:
            for m in cfg.models.values():
                m.model = self._model
        cfg.sources = list(self._sources)
        return cfg

    def build(self):
        """Build ToonicServer instance."""
        from toonic.server.main import ToonicServer
        from toonic.server.triggers.dsl import TriggerConfig, load_triggers

        cfg = self.build_config()

        trigger_config = None
        if self._triggers_file and Path(self._triggers_file).exists():
            yaml_str = Path(self._triggers_file).read_text()
            trigger_config = load_triggers(yaml_str)

        return ToonicServer(cfg, trigger_config=trigger_config)

    async def run(self) -> None:
        """Build and run server (blocking)."""
        server = self.build()
        await serve(server, web=not self._no_web, host=self._host, port=self._port)


# ══════════════════════════════════════════════════════════════
# Top-level convenience functions
# ══════════════════════════════════════════════════════════════

def watch(*sources: Union[str, SourceConfig, Dict]) -> ConfigBuilder:
    """Start building a monitoring config from one or more sources.

    Returns a ConfigBuilder for fluent chaining:
        srv = watch("./src/", "log:./app.log").goal("find bugs").build()
    """
    builder = ConfigBuilder()
    for src in sources:
        builder.add(src)
    return builder


async def monitor(
    *sources: Union[str, SourceConfig, Dict],
    goal: str = "analyze and monitor",
    interval: float = 30.0,
    model: str = "",
    web: bool = True,
    port: int = 8900,
    **kwargs,
) -> None:
    """One-liner: start monitoring sources immediately.

    Usage:
        await monitor("log:./app.log", goal="detect errors", interval=10)
        await monitor("./src/", "log:./app.log", "docker:*", goal="full-stack")
    """
    builder = watch(*sources).goal(goal).interval(interval).port(port)
    if model:
        builder.model(model)
    if not web:
        builder.no_web()
    server = builder.build()
    await serve(server, web=web, host=builder._host, port=port)


async def serve(server, web: bool = True, host: str = "0.0.0.0", port: int = 8900) -> None:
    """Run a ToonicServer instance (blocking).

    Starts Web UI by default. Use web=False for headless mode.
    """
    await server.start()

    if web:
        try:
            from toonic.server.transport.rest_api import create_app
            import uvicorn
        except ImportError:
            logger.warning("FastAPI/uvicorn not installed — running headless")
            web = False

    if web:
        app = create_app(server)
        print(f"\n  Toonic Server")
        print(f"  Web UI:  http://{host}:{port}/")
        print(f"  Goal:    {server.config.goal}")
        print(f"  Sources: {len(server.config.sources)}")
        uvi_config = uvicorn.Config(app, host=host, port=port, log_level="info")
        uvi_server = uvicorn.Server(uvi_config)
        try:
            await uvi_server.serve()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await server.stop()
    else:
        print(f"  Toonic Server (headless)")
        print(f"  Goal:    {server.config.goal}")
        print(f"  Sources: {len(server.config.sources)}")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await server.stop()


# ══════════════════════════════════════════════════════════════
# Sync entry point for scripts
# ══════════════════════════════════════════════════════════════

def run(*sources: Union[str, SourceConfig, Dict], goal: str = "analyze and monitor", **kwargs) -> None:
    """Synchronous entry point — calls asyncio.run(monitor(...)).

    Usage (in a script):
        from toonic.server.quick import run
        run("./src/", "log:./app.log", goal="find bugs")
    """
    asyncio.run(monitor(*sources, goal=goal, **kwargs))
