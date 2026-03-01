"""
ConfigBuilder - fluent API for building server configurations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from toonic.server.config import ModelConfig, ServerConfig, SourceConfig
from toonic.server.quick.parsing import parse_source

logger = logging.getLogger("toonic.quick.builder")


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

    def add(self, source: Union[str, SourceConfig, Dict], **options) -> "ConfigBuilder":
        """Add a data source. Auto-detects category from prefix/extension."""
        src = parse_source(source)
        if options:
            src.options.update({k: str(v) for k, v in options.items()})
        self._sources.append(src)
        return self

    def code(self, path: str, **opts) -> "ConfigBuilder":
        """Add code source."""
        return self.add(SourceConfig(
            path_or_url=path,
            category="code",
            options={k: str(v) for k, v in opts.items()}
        ))

    def logs(self, path: str, **opts) -> "ConfigBuilder":
        """Add log source."""
        return self.add(SourceConfig(
            path_or_url=path,
            category="logs",
            options={k: str(v) for k, v in opts.items()}
        ))

    def video(self, url: str, **opts) -> "ConfigBuilder":
        """Add video/RTSP source."""
        return self.add(SourceConfig(
            path_or_url=url,
            category="video",
            options={k: str(v) for k, v in opts.items()}
        ))

    def docker(self, filter: str = "*", **opts) -> "ConfigBuilder":
        """Add Docker container monitoring."""
        return self.add(SourceConfig(
            path_or_url=f"docker:{filter}",
            category="container",
            options={k: str(v) for k, v in opts.items()}
        ))

    def database(self, dsn: str, **opts) -> "ConfigBuilder":
        """Add database monitoring."""
        return self.add(SourceConfig(
            path_or_url=dsn,
            category="database",
            options={k: str(v) for k, v in opts.items()}
        ))

    def network(self, targets: str, **opts) -> "ConfigBuilder":
        """Add network monitoring (comma-separated hosts)."""
        return self.add(SourceConfig(
            path_or_url=f"net:{targets}",
            category="network",
            options={k: str(v) for k, v in opts.items()}
        ))

    def process(self, target: str, **opts) -> "ConfigBuilder":
        """Add process/port/service monitoring."""
        return self.add(SourceConfig(
            path_or_url=target,
            category="process",
            options={k: str(v) for k, v in opts.items()}
        ))

    def http(self, url: str, **opts) -> "ConfigBuilder":
        """Add HTTP API endpoint monitoring."""
        return self.add(SourceConfig(
            path_or_url=url,
            category="api",
            options={k: str(v) for k, v in opts.items()}
        ))

    def directory(self, path: str, **opts) -> "ConfigBuilder":
        """Add directory structure monitoring."""
        return self.add(SourceConfig(
            path_or_url=f"dir:{path}",
            category="infra",
            options={k: str(v) for k, v in opts.items()}
        ))

    # ── Config methods ──

    def goal(self, goal: str) -> "ConfigBuilder":
        """Set analysis goal."""
        self._goal = goal
        return self

    def interval(self, seconds: float) -> "ConfigBuilder":
        """Set analysis interval (0 = one-shot)."""
        self._interval = seconds
        return self

    def model(self, model_name: str) -> "ConfigBuilder":
        """Set LLM model."""
        self._model = model_name
        return self

    def port(self, port: int) -> "ConfigBuilder":
        """Set HTTP port."""
        self._port = port
        return self

    def host(self, host: str) -> "ConfigBuilder":
        """Set server host."""
        self._host = host
        return self

    def tokens(self, max_tokens: int, allocation: Optional[Dict[str, float]] = None) -> "ConfigBuilder":
        """Set token budget and optional per-category allocation."""
        self._max_tokens = max_tokens
        if allocation:
            self._token_alloc = allocation
        return self

    def when(self, condition: str) -> "ConfigBuilder":
        """Set NLP trigger condition (e.g. 'error occurs 5 times in 60s')."""
        self._when = condition
        return self

    def triggers(self, yaml_path: str) -> "ConfigBuilder":
        """Load trigger rules from YAML file."""
        self._triggers_file = yaml_path
        return self

    def no_web(self) -> "ConfigBuilder":
        """Disable web UI."""
        self._no_web = True
        return self

    def no_history(self) -> "ConfigBuilder":
        """Disable history database."""
        self._history = False
        return self

    def log_level(self, level: str) -> "ConfigBuilder":
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
        from toonic.server.quick.runtime import serve

        server = self.build()
        await serve(server, web=not self._no_web, host=self._host, port=self._port)
