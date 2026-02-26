"""
Infrastructure handlers — Kubernetes, GitHub Actions
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
# Model: Infrastructure
# =============================================================================

@dataclass
class InfraResource:
    """Zasób infrastrukturalny."""
    kind: str
    name: str
    namespace: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InfraLogic:
    """Logika infrastruktury — Kubernetes, Terraform, CI/CD."""
    source_file: str
    source_hash: str
    file_category: str = "infra"

    infra_type: str = "kubernetes"
    resources: List[InfraResource] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "infra_type": self.infra_type,
            "resources": [
                {"kind": r.kind, "name": r.name, "namespace": r.namespace,
                 "properties": r.properties}
                for r in self.resources
            ],
        }

    def complexity(self) -> int:
        return sum(len(r.properties) + 1 for r in self.resources)


# =============================================================================
# Kubernetes Handler
# =============================================================================

class KubernetesHandler(BaseHandlerMixin):
    """Handler dla manifestów Kubernetes."""

    extensions = frozenset({'.yaml', '.yml'})
    category = 'infra'
    requires = ()

    def parse(self, path: Path) -> InfraLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        resources = []
        docs = content.split('\n---')
        for doc in docs:
            kind_match = re.search(r'kind:\s*(\w+)', doc)
            name_match = re.search(r'name:\s*(\S+)', doc)
            ns_match = re.search(r'namespace:\s*(\S+)', doc)

            if kind_match:
                props = {}
                replicas_match = re.search(r'replicas:\s*(\d+)', doc)
                if replicas_match:
                    props['replicas'] = int(replicas_match.group(1))
                image_match = re.search(r'image:\s*(\S+)', doc)
                if image_match:
                    props['image'] = image_match.group(1)
                port_matches = re.findall(r'containerPort:\s*(\d+)', doc)
                if port_matches:
                    props['ports'] = [int(p) for p in port_matches]

                resources.append(InfraResource(
                    kind=kind_match.group(1),
                    name=name_match.group(1) if name_match else "",
                    namespace=ns_match.group(1) if ns_match else "default",
                    properties=props,
                ))

        return InfraLogic(
            source_file=path.name,
            source_hash=source_hash,
            infra_type='kubernetes',
            resources=resources,
        )

    def to_spec(self, logic: InfraLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | kubernetes | {len(logic.resources)} resources"]
            for r in logic.resources:
                props_str = ", ".join(f"{k}:{v}" for k, v in r.properties.items())
                ns = f" ns:{r.namespace}" if r.namespace != "default" else ""
                lines.append(f"  {r.kind}/{r.name}{ns} | {props_str}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: InfraLogic, client: Any = None, target_fmt: str | None = None) -> str:
        docs = []
        for r in logic.resources:
            doc = [
                f"apiVersion: apps/v1",
                f"kind: {r.kind}",
                f"metadata:",
                f"  name: {r.name}",
            ]
            if r.namespace:
                doc.append(f"  namespace: {r.namespace}")
            if r.properties:
                doc.append("spec:")
                for k, v in r.properties.items():
                    doc.append(f"  {k}: {v}")
            docs.append('\n'.join(doc))
        return '\n---\n'.join(docs)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if 'apiVersion:' in content[:500]:
            score += 0.5
        if 'kind:' in content[:500]:
            score += 0.3
        if 'metadata:' in content[:1000]:
            score += 0.2
        return min(score, 1.0)


# =============================================================================
# GitHub Actions Handler
# =============================================================================

class GithubActionsHandler(BaseHandlerMixin):
    """Handler dla GitHub Actions workflow."""

    extensions = frozenset({'.yaml', '.yml'})
    category = 'cicd'
    requires = ()

    def parse(self, path: Path) -> InfraLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        resources = []
        in_jobs = False
        for line in content.split('\n'):
            if line.strip() == 'jobs:':
                in_jobs = True
                continue
            if in_jobs:
                job_match = re.match(r'^  (\w[\w-]*):\s*$', line)
                if job_match:
                    job_name = job_match.group(1)
                    runs_on = ""
                    runs_match = re.search(
                        rf'{job_name}:.*?runs-on:\s*(\S+)',
                        content, re.DOTALL
                    )
                    if runs_match:
                        runs_on = runs_match.group(1)
                    resources.append(InfraResource(
                        kind='Job',
                        name=job_name,
                        properties={'runs-on': runs_on} if runs_on else {},
                    ))

        name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
        workflow_name = name_match.group(1).strip().strip("'\"") if name_match else path.stem

        return InfraLogic(
            source_file=path.name,
            source_hash=source_hash,
            infra_type='github-actions',
            resources=resources,
            metadata={'workflow_name': workflow_name},
        )

    def to_spec(self, logic: InfraLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            wf_name = logic.metadata.get('workflow_name', logic.source_file)
            lines = [f"# {logic.source_file} | github-actions | {len(logic.resources)} jobs"]
            lines.append(f"workflow: {wf_name}")
            for r in logic.resources:
                runs_on = r.properties.get('runs-on', '?')
                lines.append(f"  job:{r.name} | runs-on:{runs_on}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: InfraLogic, client: Any = None, target_fmt: str | None = None) -> str:
        wf_name = logic.metadata.get('workflow_name', 'CI')
        lines = [f"name: {wf_name}", "", "on:", "  push:", "    branches: [main]", "", "jobs:"]
        for r in logic.resources:
            runs_on = r.properties.get('runs-on', 'ubuntu-latest')
            lines.extend([
                f"  {r.name}:",
                f"    runs-on: {runs_on}",
                f"    steps:",
                f"      - uses: actions/checkout@v4",
            ])
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        if '.github/workflows' in str(path):
            score += 0.6
        if 'on:' in content[:300] and 'jobs:' in content:
            score += 0.3
        if 'runs-on:' in content:
            score += 0.2
        if 'uses:' in content:
            score += 0.1
        if 'apiVersion:' in content[:200]:
            score -= 0.5
        return max(min(score, 1.0), 0.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_infra_handlers() -> None:
    """Rejestruje handlery infrastruktury."""
    for handler in [KubernetesHandler(), GithubActionsHandler()]:
        FormatRegistry.register(handler)
