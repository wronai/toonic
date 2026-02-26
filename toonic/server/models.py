"""
Server data models — messages exchanged between components.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceCategory(str, Enum):
    CODE = "code"
    CONFIG = "config"
    DATA = "data"
    LOGS = "logs"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    DATABASE = "database"
    API = "api"
    INFRA = "infra"
    WEB = "web"
    NETWORK = "network"
    CONTAINER = "container"
    PROCESS = "process"


@dataclass
class ContextChunk:
    """Single chunk of context from a data source."""
    source_id: str
    category: SourceCategory
    toon_spec: str = ""
    raw_data: bytes = b""
    raw_encoding: str = "text"      # text|base64_jpeg|base64_ulaw
    timestamp: float = 0.0
    is_delta: bool = False
    token_estimate: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.token_estimate and self.toon_spec:
            self.token_estimate = len(self.toon_spec.split()) * 4 // 3

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "source_id": self.source_id,
            "category": self.category.value if isinstance(self.category, SourceCategory) else self.category,
            "toon_spec": self.toon_spec,
            "timestamp": self.timestamp,
            "is_delta": self.is_delta,
            "token_estimate": self.token_estimate,
        }
        if self.raw_data:
            import base64
            d["raw_data"] = base64.b64encode(self.raw_data).decode()
            d["raw_encoding"] = self.raw_encoding
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class ActionResponse:
    """LLM response → action to execute."""
    action_id: str = ""
    action_type: str = "none"       # code_fix|report|alert|none
    content: str = ""
    target_path: str = ""
    confidence: float = 0.0
    affected_files: List[str] = field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0
    duration_s: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "content": self.content,
            "target_path": self.target_path,
            "confidence": self.confidence,
            "affected_files": self.affected_files,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "duration_s": self.duration_s,
        }


@dataclass
class ServerEvent:
    """Event emitted by the server to clients."""
    event_type: str                  # context|action|status|error|log
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }
