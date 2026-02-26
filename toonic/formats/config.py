"""
Config handlers — Dockerfile, .env
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from toonic.core.base import BaseHandlerMixin
from toonic.core.registry import FormatRegistry


# =============================================================================
# Modele logiki — Konfiguracja
# =============================================================================

@dataclass
class ConfigEntry:
    """Pojedynczy wpis konfiguracyjny."""
    key: str
    value_type: str = "string"
    category: str = ""
    sensitive: bool = False
    description: str = ""


@dataclass
class ConfigLogic:
    """Logika pliku konfiguracyjnego."""
    source_file: str
    source_hash: str
    file_category: str = "config"

    config_type: str = "env"
    entries: List[ConfigEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "config_type": self.config_type,
            "entries": [
                {"key": e.key, "type": e.value_type, "category": e.category,
                 "sensitive": e.sensitive}
                for e in self.entries
            ],
        }

    def complexity(self) -> int:
        return len(self.entries)


# =============================================================================
# Dockerfile Handler
# =============================================================================

class DockerfileHandler(BaseHandlerMixin):
    """Handler dla Dockerfile."""

    extensions = frozenset(set())
    category = 'config'
    requires = ()

    def parse(self, path: Path) -> ConfigLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        entries = []
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(None, 1)
            if parts:
                instruction = parts[0].upper()
                value = parts[1] if len(parts) > 1 else ""
                category = {
                    'FROM': 'build', 'RUN': 'build', 'COPY': 'build', 'ADD': 'build',
                    'ENV': 'runtime', 'EXPOSE': 'network', 'CMD': 'runtime',
                    'ENTRYPOINT': 'runtime', 'WORKDIR': 'build', 'ARG': 'build',
                    'LABEL': 'metadata', 'VOLUME': 'storage', 'USER': 'security',
                    'HEALTHCHECK': 'runtime',
                }.get(instruction, 'other')
                entries.append(ConfigEntry(
                    key=instruction,
                    value_type='command',
                    category=category,
                    description=value[:80],
                ))

        return ConfigLogic(
            source_file=path.name,
            source_hash=source_hash,
            config_type='dockerfile',
            entries=entries,
        )

    def to_spec(self, logic: ConfigLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | dockerfile | {len(logic.entries)} instructions"]
            by_cat: Dict[str, List[ConfigEntry]] = {}
            for e in logic.entries:
                by_cat.setdefault(e.category, []).append(e)
            for cat, entries in by_cat.items():
                parts = [f"{e.key}={e.description[:30]}" for e in entries]
                lines.append(f"  {cat}: {', '.join(parts)}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: ConfigLogic, client: Any = None, target_fmt: str | None = None) -> str:
        lines = []
        for e in logic.entries:
            lines.append(f"{e.key} {e.description}")
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if path.name.lower() in ('dockerfile', 'dockerfile.dev', 'dockerfile.prod'):
            score += 0.8
        if 'FROM ' in content[:200]:
            score += 0.3
        if 'RUN ' in content or 'COPY ' in content:
            score += 0.2
        return min(score, 1.0)


# =============================================================================
# Env Handler
# =============================================================================

class EnvHandler(BaseHandlerMixin):
    """Handler dla plików .env."""

    extensions = frozenset({'.env'})
    category = 'config'
    requires = ()

    SENSITIVE_PATTERNS = re.compile(
        r'(key|secret|password|token|auth|credential|private)', re.IGNORECASE
    )

    def parse(self, path: Path) -> ConfigLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        entries = []
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"\'')
                sensitive = bool(self.SENSITIVE_PATTERNS.search(key))
                entries.append(ConfigEntry(
                    key=key,
                    value_type=self._infer_type(value),
                    category=self._categorize(key),
                    sensitive=sensitive,
                    description='***' if sensitive else value[:50],
                ))

        return ConfigLogic(
            source_file=path.name,
            source_hash=source_hash,
            config_type='env',
            entries=entries,
        )

    def _infer_type(self, value: str) -> str:
        if value.lower() in ('true', 'false'):
            return 'bool'
        if value.isdigit():
            return 'int'
        return 'string'

    def _categorize(self, key: str) -> str:
        key_upper = key.upper()
        if any(x in key_upper for x in ['DB_', 'DATABASE', 'REDIS', 'MONGO']):
            return 'database'
        if any(x in key_upper for x in ['PORT', 'HOST', 'URL', 'DOMAIN']):
            return 'network'
        if any(x in key_upper for x in ['KEY', 'SECRET', 'TOKEN', 'AUTH']):
            return 'security'
        if any(x in key_upper for x in ['LOG', 'DEBUG', 'ENV', 'MODE']):
            return 'runtime'
        return 'other'

    def to_spec(self, logic: ConfigLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | env | {len(logic.entries)} vars"]
            by_cat: Dict[str, List[ConfigEntry]] = {}
            for e in logic.entries:
                by_cat.setdefault(e.category, []).append(e)
            for cat, entries in by_cat.items():
                parts = []
                for e in entries:
                    display = '***' if e.sensitive else e.description[:20]
                    parts.append(f"{e.key}={display}")
                lines.append(f"  {cat}[{len(entries)}]: {', '.join(parts)}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: ConfigLogic, client: Any = None, target_fmt: str | None = None) -> str:
        lines = []
        for e in logic.entries:
            if e.sensitive:
                lines.append(f"{e.key}=CHANGE_ME")
            else:
                lines.append(f"{e.key}={e.description}")
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if path.name.startswith('.env'):
            score += 0.7
        env_lines = [l for l in content.split('\n')[:20]
                     if l.strip() and not l.startswith('#')]
        if env_lines and all('=' in l for l in env_lines):
            score += 0.3
        return min(score, 1.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_config_handlers() -> None:
    """Rejestruje handlery konfiguracji."""
    for handler in [DockerfileHandler(), EnvHandler()]:
        FormatRegistry.register(handler)
