"""
Server configuration — YAML/env-based config for Toonic Server.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_dotenv() -> None:
    """Load .env file if present (without python-dotenv dependency)."""
    for env_path in [".env", "../.env"]:
        p = Path(env_path)
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    # Resolve ${VAR} references
                    if "${" in val:
                        import re
                        for m in re.finditer(r'\$\{(\w+)\}', val):
                            val = val.replace(m.group(0), os.environ.get(m.group(1), ""))
                    if key and key not in os.environ:
                        os.environ[key] = val
            break


_load_dotenv()


@dataclass
class ModelConfig:
    """LLM model configuration."""
    provider: str = "openrouter"
    model: str = "google/gemini-3-flash-preview"
    max_tokens: int = 8192
    supports: List[str] = field(default_factory=lambda: ["text"])
    api_key_env: str = "LLM_API_KEY"
    base_url: str = ""


@dataclass
class SourceConfig:
    """Data source configuration."""
    source_id: str = ""
    category: str = "code"           # code|config|data|logs|video|audio|document|database|api|web|network|container|process|infra
    path_or_url: str = ""
    watch: bool = True
    poll_interval: float = 2.0
    options: Dict[str, str] = field(default_factory=dict)


@dataclass
class ServerConfig:
    """Main server configuration."""
    host: str = "0.0.0.0"
    port: int = 8900
    ws_port: int = 8901
    
    # Goal
    goal: str = "analyze project structure and suggest improvements"
    goal_type: str = "analyze"       # fix|analyze|optimize|monitor
    interval: float = 30.0           # seconds between LLM calls, 0=one-shot
    
    # Token budget
    max_context_tokens: int = 100000
    token_allocation: Dict[str, float] = field(default_factory=lambda: {
        "code": 0.40,
        "config": 0.05,
        "logs": 0.15,
        "video": 0.15,
        "audio": 0.10,
        "document": 0.05,
        "system": 0.10,
    })
    
    # Models
    models: Dict[str, ModelConfig] = field(default_factory=lambda: {
        "text": ModelConfig(
            provider=os.environ.get("LLM_PROVIDER", "openrouter"),
            model=os.environ.get("LLM_MODEL", "google/gemini-3-flash-preview"),
        ),
        "code": ModelConfig(
            provider=os.environ.get("LLM_PROVIDER", "openrouter"),
            model=os.environ.get("LLM_MODEL", "google/gemini-3-flash-preview"),
        ),
        "multimodal": ModelConfig(
            provider=os.environ.get("LLM_PROVIDER", "openrouter"),
            model=os.environ.get("LLM_MODEL", "google/gemini-3-flash-preview"),
            supports=["text", "image", "audio"],
        ),
    })
    
    # Sources
    sources: List[SourceConfig] = field(default_factory=list)
    
    # History
    history_enabled: bool = True
    history_db_path: str = "./toonic_history.db"
    
    # Logging
    log_level: str = "INFO"
    log_file: str = ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ServerConfig:
        """Create config from dict (parsed YAML/JSON)."""
        cfg = cls()
        for key, val in data.items():
            if key == "models" and isinstance(val, dict):
                cfg.models = {k: ModelConfig(**v) if isinstance(v, dict) else v for k, v in val.items()}
            elif key == "sources" and isinstance(val, list):
                cfg.sources = [SourceConfig(**s) if isinstance(s, dict) else s for s in val]
            elif hasattr(cfg, key):
                setattr(cfg, key, val)
        return cfg
    
    @classmethod
    def from_yaml_file(cls, path: str) -> ServerConfig:
        """Load config from YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data or {})
    
    @classmethod
    def from_env(cls) -> ServerConfig:
        """Load config from environment variables."""
        cfg = cls()
        cfg.host = os.environ.get("TOONIC_HOST", cfg.host)
        cfg.port = int(os.environ.get("TOONIC_PORT", cfg.port))
        cfg.goal = os.environ.get("TOONIC_GOAL", cfg.goal)
        cfg.interval = float(os.environ.get("TOONIC_INTERVAL", cfg.interval))
        cfg.log_level = os.environ.get("TOONIC_LOG_LEVEL", cfg.log_level)
        
        # Default model from env
        model = os.environ.get("LLM_MODEL", "")
        if model:
            for m in cfg.models.values():
                m.model = model
        
        # History
        cfg.history_enabled = os.environ.get("TOONIC_HISTORY_ENABLED", "true").lower() == "true"
        cfg.history_db_path = os.environ.get("TOONIC_DB_PATH", cfg.history_db_path)
        
        return cfg
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "host": self.host,
            "port": self.port,
            "ws_port": self.ws_port,
            "goal": self.goal,
            "goal_type": self.goal_type,
            "interval": self.interval,
            "max_context_tokens": self.max_context_tokens,
            "models": {k: {"provider": v.provider, "model": v.model, "max_tokens": v.max_tokens}
                       for k, v in self.models.items()},
            "sources": [{"source_id": s.source_id, "category": s.category,
                        "path_or_url": s.path_or_url} for s in self.sources],
        }
