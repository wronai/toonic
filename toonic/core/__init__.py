"""
Toonic Core — Protocols, Registry, and Base Models
===================================================

Defines the fundamental abstractions:
- FileLogic Protocol — minimal data interface for file logic
- FileHandler Protocol — one handler per file type
- FormatRegistry — central registry with two-stage resolution
- SpecDetector — detects logic type from spec headers
- BaseHandlerMixin — shared utilities for handlers
"""

from toonic.core.protocols import FileLogic, FileHandler
from toonic.core.registry import FormatRegistry
from toonic.core.base import BaseHandlerMixin
from toonic.core.detector import SpecDetector
from toonic.core.models import CodeLogicBase

__all__ = [
    "FileLogic",
    "FileHandler",
    "FormatRegistry",
    "BaseHandlerMixin",
    "SpecDetector",
    "CodeLogicBase",
]
