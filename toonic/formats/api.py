"""
API handlers — OpenAPI/Swagger
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
# Model: API
# =============================================================================

@dataclass
class EndpointSpec:
    """Specyfikacja endpointu API."""
    method: str
    path: str
    summary: str = ""
    parameters: List[str] = field(default_factory=list)
    request_body: str = ""
    response_type: str = ""
    auth_required: bool = False


@dataclass
class ApiLogic:
    """Logika API — OpenAPI, GraphQL."""
    source_file: str
    source_hash: str
    file_category: str = "api"

    api_type: str = "openapi"
    version: str = ""
    title: str = ""
    base_url: str = ""
    endpoints: List[EndpointSpec] = field(default_factory=list)
    schemas: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "api_type": self.api_type,
            "version": self.version,
            "title": self.title,
            "endpoints": [
                {"method": e.method, "path": e.path, "summary": e.summary}
                for e in self.endpoints
            ],
            "schemas": self.schemas,
        }

    def complexity(self) -> int:
        return len(self.endpoints) * 3 + len(self.schemas)


# =============================================================================
# OpenAPI Handler
# =============================================================================

class OpenApiHandler(BaseHandlerMixin):
    """Handler dla OpenAPI/Swagger specs."""

    extensions = frozenset({'.yaml', '.yml', '.json'})
    category = 'api'
    requires = ()

    def parse(self, path: Path) -> ApiLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        endpoints = []
        version = ""
        title = ""

        ver_match = re.search(r'(?:openapi|swagger):\s*["\']?(\d+\.\d+)', content)
        if ver_match:
            version = ver_match.group(1)

        title_match = re.search(r'title:\s*["\']?([^"\'\n]+)', content)
        if title_match:
            title = title_match.group(1).strip()

        current_path = ""
        for line in content.split('\n'):
            path_match = re.match(r'^\s{2}(/\S+):\s*$', line)
            if path_match:
                current_path = path_match.group(1)
                continue
            method_match = re.match(r'^\s{4}(get|post|put|delete|patch|options|head):\s*$', line)
            if method_match and current_path:
                endpoints.append(EndpointSpec(
                    method=method_match.group(1).upper(),
                    path=current_path,
                ))

        schemas = re.findall(r'^\s{4}(\w+):\s*$', content, re.MULTILINE)

        return ApiLogic(
            source_file=path.name,
            source_hash=source_hash,
            api_type='openapi',
            version=version,
            title=title,
            endpoints=endpoints,
            schemas=schemas[:20],
        )

    def to_spec(self, logic: ApiLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | openapi {logic.version} | {len(logic.endpoints)} endpoints"]
            if logic.title:
                lines.append(f"title: {logic.title}")
            if logic.endpoints:
                lines.append(f"E[{len(logic.endpoints)}]:")
                for e in logic.endpoints:
                    auth = " locked" if e.auth_required else ""
                    lines.append(f"  {e.method:6s} {e.path}{auth}")
            if logic.schemas:
                lines.append(f"schemas[{len(logic.schemas)}]: {', '.join(logic.schemas[:10])}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: ApiLogic, client: Any = None, target_fmt: str | None = None) -> str:
        lines = [f"openapi: '{logic.version or '3.0.0'}'"]
        lines.append("info:")
        lines.append(f"  title: {logic.title or 'API'}")
        lines.append(f"  version: '1.0.0'")
        lines.append("paths:")
        for e in logic.endpoints:
            lines.append(f"  {e.path}:")
            lines.append(f"    {e.method.lower()}:")
            lines.append(f"      summary: '{e.summary or e.path}'")
            lines.append(f"      responses:")
            lines.append(f"        '200':")
            lines.append(f"          description: OK")
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if 'openapi:' in content[:500] or '"openapi"' in content[:500]:
            score += 0.7
        elif 'swagger:' in content[:500] or '"swagger"' in content[:500]:
            score += 0.7
        if 'paths:' in content or '"paths"' in content:
            score += 0.2
        if 'components:' in content or 'definitions:' in content:
            score += 0.1
        return min(score, 1.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_api_handlers() -> None:
    """Rejestruje handlery API."""
    for handler in [OpenApiHandler()]:
        FormatRegistry.register(handler)
