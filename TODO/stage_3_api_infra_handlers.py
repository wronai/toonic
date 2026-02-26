"""
Toonic — Etap 3: Handlery API, baz danych i infrastruktury
===========================================================

Obsługa: OpenAPI, SQL DDL, Kubernetes, GitHub Actions, docker-compose.
Content sniffing jest tu kluczowy — pliki .yaml mogą być wieloma rzeczami.

Migrowane funkcje z code2logic:
- plan v2.0 Sprint 3 (API/schematy) → ApiHandler
- plan v2.0 Sprint 4 (infrastruktura) → InfraHandler
- plan v3.0 Kategoria H (bazy danych) → SqlHandler
- file_formats.py detection logic → sniff() metody
- plan v4.0 content sniffing → rozwiązanie kolizji rozszerzeń
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from stage_0_foundation import BaseHandlerMixin, FileLogic, FormatRegistry


# =============================================================================
# Model: SQL Schema
# =============================================================================

@dataclass
class ColumnDef:
    """Definicja kolumny tabeli SQL."""
    name: str
    dtype: str              # VARCHAR(255), BIGINT, TIMESTAMP...
    nullable: bool = True
    constraints: List[str] = field(default_factory=list)  # PK, UNIQUE, CHECK(...)
    references: str = ""    # users(id) ON DELETE CASCADE


@dataclass
class TableDef:
    """Definicja tabeli SQL."""
    name: str
    schema_name: str = "public"
    columns: List[ColumnDef] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)


@dataclass
class SqlSchemaLogic:
    """Logika schematu SQL — DDL, migracje, procedury.

    Migracja z: plan v3.0 Kategoria H — SqlSchemaLogic
    """
    source_file: str
    source_hash: str
    file_category: str = "database"

    dialect: str = "postgresql"  # postgresql | mysql | sqlite | mssql
    tables: List[TableDef] = field(default_factory=list)
    views: List[str] = field(default_factory=list)
    stored_procedures: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "dialect": self.dialect,
            "tables": [
                {
                    "name": t.name,
                    "columns": [{"name": c.name, "type": c.dtype, "constraints": c.constraints}
                                for c in t.columns],
                    "indexes": t.indexes,
                }
                for t in self.tables
            ],
            "views": self.views,
        }

    def complexity(self) -> int:
        return sum(len(t.columns) for t in self.tables) + len(self.views) * 2


# =============================================================================
# Model: API
# =============================================================================

@dataclass
class EndpointSpec:
    """Specyfikacja endpointu API."""
    method: str         # GET, POST, PUT, DELETE
    path: str           # /api/v1/users
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

    api_type: str = "openapi"   # openapi | graphql | protobuf
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
# Model: Infrastructure
# =============================================================================

@dataclass
class InfraResource:
    """Zasób infrastrukturalny."""
    kind: str           # Deployment, Service, ConfigMap, aws_instance, ...
    name: str
    namespace: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InfraLogic:
    """Logika infrastruktury — Kubernetes, Terraform, CI/CD."""
    source_file: str
    source_hash: str
    file_category: str = "infra"

    infra_type: str = "kubernetes"  # kubernetes | terraform | github-actions | gitlab-ci | docker-compose
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
# SQL Handler
# =============================================================================

class SqlHandler(BaseHandlerMixin):
    """Handler dla SQL DDL/DML.

    Migracja z: plan v3.0 Kategoria H
    """

    extensions = frozenset({'.sql'})
    category = 'database'
    requires = ()

    def parse(self, path: Path) -> SqlSchemaLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        # Wykryj dialekt
        dialect = 'postgresql'
        if 'AUTO_INCREMENT' in content.upper():
            dialect = 'mysql'
        elif 'AUTOINCREMENT' in content.upper():
            dialect = 'sqlite'

        tables = self._extract_tables(content)
        views = re.findall(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)', content, re.IGNORECASE)
        procedures = re.findall(r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+(\w+)',
                                content, re.IGNORECASE)

        return SqlSchemaLogic(
            source_file=path.name,
            source_hash=source_hash,
            dialect=dialect,
            tables=tables,
            views=views,
            stored_procedures=procedures,
        )

    def _extract_tables(self, content: str) -> List[TableDef]:
        """Ekstrakcja definicji tabel z SQL DDL."""
        tables = []
        pattern = re.compile(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
            r'(?:(\w+)\.)?(\w+)\s*\((.*?)\)\s*;',
            re.IGNORECASE | re.DOTALL
        )

        for match in pattern.finditer(content):
            schema_name = match.group(1) or 'public'
            table_name = match.group(2)
            body = match.group(3)

            columns = self._extract_columns(body)
            tables.append(TableDef(
                name=table_name,
                schema_name=schema_name,
                columns=columns,
            ))

        return tables

    def _extract_columns(self, body: str) -> List[ColumnDef]:
        """Ekstrakcja kolumn z ciała CREATE TABLE."""
        columns = []
        # Podziel po przecinkach, ale nie wewnątrz nawiasów
        depth = 0
        current = []
        parts = []
        for char in body:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
                continue
            current.append(char)
        if current:
            parts.append(''.join(current).strip())

        for part in parts:
            part = part.strip()
            # Pomiń constraint-y na poziomie tabeli
            if re.match(r'^(PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|CONSTRAINT)', part, re.IGNORECASE):
                continue

            tokens = part.split()
            if len(tokens) < 2:
                continue

            col_name = tokens[0].strip('"\'`')
            dtype = tokens[1]

            # Zbierz dodatkowe tokeny jako constraints
            constraints = []
            nullable = True
            references = ""
            rest = ' '.join(tokens[2:]).upper()

            if 'PRIMARY KEY' in rest:
                constraints.append('PK')
            if 'NOT NULL' in rest:
                nullable = False
                constraints.append('NN')
            if 'UNIQUE' in rest:
                constraints.append('UNIQUE')
            if 'REFERENCES' in rest:
                ref_match = re.search(r'REFERENCES\s+(\w+\(.*?\))', rest, re.IGNORECASE)
                if ref_match:
                    references = ref_match.group(1)
                    constraints.append(f'FK→{references}')

            columns.append(ColumnDef(
                name=col_name,
                dtype=dtype,
                nullable=nullable,
                constraints=constraints,
                references=references,
            ))

        return columns

    def to_spec(self, logic: SqlSchemaLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            return self._to_toon(logic)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def _to_toon(self, s: SqlSchemaLogic) -> str:
        """
        # schema.sql | postgresql | 6 tables | 3 views
        T[6]:
          users     | id:bigserial PK, email:varchar UNIQUE NN, created:timestamptz
          profiles  | user_id:bigint FK→users(id), bio:text
        V[3]: active_users, post_stats, user_activity
        """
        lines = [f"# {s.source_file} | {s.dialect} | {len(s.tables)} tables"]
        if s.views:
            lines[0] += f" | {len(s.views)} views"

        if s.tables:
            lines.append(f"T[{len(s.tables)}]:")
            for t in s.tables:
                col_parts = []
                for c in t.columns:
                    part = f"{c.name}:{c.dtype}"
                    if c.constraints:
                        part += " " + " ".join(c.constraints)
                    col_parts.append(part)
                lines.append(f"  {t.name:15s} | {', '.join(col_parts)}")

        if s.views:
            lines.append(f"V[{len(s.views)}]: {', '.join(s.views)}")

        if s.stored_procedures:
            lines.append(f"proc[{len(s.stored_procedures)}]: {', '.join(s.stored_procedures)}")

        return '\n'.join(lines)

    def reproduce(self, logic: SqlSchemaLogic, client: Any = None, target_fmt: str | None = None) -> str:
        """Reprodukuje SQL DDL z logiki."""
        lines = []
        for t in logic.tables:
            col_lines = []
            for c in t.columns:
                parts = [f"    {c.name} {c.dtype}"]
                if 'PK' in c.constraints:
                    parts.append("PRIMARY KEY")
                if 'NN' in c.constraints or not c.nullable:
                    parts.append("NOT NULL")
                if 'UNIQUE' in c.constraints:
                    parts.append("UNIQUE")
                if c.references:
                    parts.append(f"REFERENCES {c.references}")
                col_lines.append(' '.join(parts))
            lines.append(f"CREATE TABLE {t.name} (")
            lines.append(',\n'.join(col_lines))
            lines.append(");\n")
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        upper = content.upper()
        if 'CREATE TABLE' in upper:
            score += 0.6
        if 'ALTER TABLE' in upper or 'DROP TABLE' in upper:
            score += 0.2
        if 'SELECT' in upper and 'FROM' in upper:
            score += 0.2
        return min(score, 1.0)


# =============================================================================
# OpenAPI Handler
# =============================================================================

class OpenApiHandler(BaseHandlerMixin):
    """Handler dla OpenAPI/Swagger specs.

    Content sniffing kluczowy — pliki .yaml/.json mogą być czymkolwiek.
    """

    extensions = frozenset({'.yaml', '.yml', '.json'})
    category = 'api'
    requires = ()

    def parse(self, path: Path) -> ApiLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        # Prosty parser YAML/JSON dla OpenAPI
        endpoints = []
        version = ""
        title = ""

        # Wykryj wersję
        ver_match = re.search(r'(?:openapi|swagger):\s*["\']?(\d+\.\d+)', content)
        if ver_match:
            version = ver_match.group(1)

        # Wykryj tytuł
        title_match = re.search(r'title:\s*["\']?([^"\'\n]+)', content)
        if title_match:
            title = title_match.group(1).strip()

        # Ekstrakcja endpointów (uproszczona)
        path_pattern = re.compile(
            r'^\s{2}(/\S+):\s*$',  # ścieżka na 2-spacyjnym wcięciu
            re.MULTILINE
        )
        method_pattern = re.compile(
            r'^\s{4}(get|post|put|delete|patch|options|head):\s*$',
            re.MULTILINE
        )

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

        # Schematy
        schemas = re.findall(r'^\s{4}(\w+):\s*$', content, re.MULTILINE)

        return ApiLogic(
            source_file=path.name,
            source_hash=source_hash,
            api_type='openapi',
            version=version,
            title=title,
            endpoints=endpoints,
            schemas=schemas[:20],  # max 20
        )

    def to_spec(self, logic: ApiLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | openapi {logic.version} | {len(logic.endpoints)} endpoints"]
            if logic.title:
                lines.append(f"title: {logic.title}")
            if logic.endpoints:
                lines.append(f"E[{len(logic.endpoints)}]:")
                for e in logic.endpoints:
                    auth = " 🔒" if e.auth_required else ""
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
        """Wykryj OpenAPI — kluczowe: 'openapi:', 'swagger:', 'paths:'."""
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
        # Multi-doc YAML (---)
        docs = content.split('\n---')
        for doc in docs:
            kind_match = re.search(r'kind:\s*(\w+)', doc)
            name_match = re.search(r'name:\s*(\S+)', doc)
            ns_match = re.search(r'namespace:\s*(\S+)', doc)

            if kind_match:
                props = {}
                # Ekstrakcja podstawowych properties
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
        """Kubernetes detection — apiVersion + kind + metadata."""
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
        # Ekstrakcja jobów
        job_pattern = re.compile(r'^\s{2}(\w[\w-]*):\s*$', re.MULTILINE)
        in_jobs = False
        for line in content.split('\n'):
            if line.strip() == 'jobs:':
                in_jobs = True
                continue
            if in_jobs:
                job_match = re.match(r'^  (\w[\w-]*):\s*$', line)
                if job_match:
                    job_name = job_match.group(1)
                    # Szukaj runs-on
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

        # Workflow name
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
        """GitHub Actions — lokalizacja + treść."""
        score = 0.0
        if '.github/workflows' in str(path):
            score += 0.6
        if 'on:' in content[:300] and 'jobs:' in content:
            score += 0.3
        if 'runs-on:' in content:
            score += 0.2
        if 'uses:' in content:
            score += 0.1
        # Negatywne
        if 'apiVersion:' in content[:200]:
            score -= 0.5
        return max(min(score, 1.0), 0.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_api_infra_handlers() -> None:
    """Rejestruje handlery API, baz danych i infrastruktury."""
    for handler in [
        SqlHandler(),
        OpenApiHandler(),
        KubernetesHandler(),
        GithubActionsHandler(),
    ]:
        FormatRegistry.register(handler)


# =============================================================================
# Testy
# =============================================================================

if __name__ == '__main__':
    import tempfile, os

    print("=== Toonic Stage 3: API & Infra Handlers Tests ===\n")

    FormatRegistry.reset()
    register_api_infra_handlers()

    # Test SQL
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write("""
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE posts (
    id BIGSERIAL PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    body TEXT
);

CREATE VIEW active_users AS SELECT * FROM users WHERE created_at > NOW() - INTERVAL '30 days';
""")
        sql_path = Path(f.name)
        f.flush()

    sql_handler = FormatRegistry.resolve(sql_path)
    assert isinstance(sql_handler, SqlHandler)
    sql_logic = sql_handler.parse(sql_path)
    assert sql_logic.dialect == 'postgresql'
    assert len(sql_logic.tables) == 2
    assert len(sql_logic.views) == 1
    toon = sql_handler.to_spec(sql_logic, 'toon')
    print(f"✓ SQL: {len(sql_logic.tables)} tables, {len(sql_logic.views)} views, dialect={sql_logic.dialect}")
    print(f"  TOON:\n{toon}\n")

    # Test content sniffing — Kubernetes vs GitHub Actions
    k8s_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: myapp
        image: myapp:v2.1
        ports:
        - containerPort: 8080
"""
    gh_content = """name: CI
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

    k8s_handler = KubernetesHandler()
    gh_handler = GithubActionsHandler()

    k8s_score = k8s_handler.sniff(Path("deployment.yaml"), k8s_content)
    gh_score_on_k8s = gh_handler.sniff(Path("deployment.yaml"), k8s_content)
    assert k8s_score > gh_score_on_k8s, f"K8s sniff ({k8s_score}) should beat GH ({gh_score_on_k8s})"
    print(f"✓ Content sniffing: K8s={k8s_score:.1f} > GH={gh_score_on_k8s:.1f} for deployment.yaml")

    gh_score = gh_handler.sniff(Path(".github/workflows/ci.yml"), gh_content)
    k8s_score_on_gh = k8s_handler.sniff(Path(".github/workflows/ci.yml"), gh_content)
    assert gh_score > k8s_score_on_gh, f"GH sniff ({gh_score}) should beat K8s ({k8s_score_on_gh})"
    print(f"✓ Content sniffing: GH={gh_score:.1f} > K8s={k8s_score_on_gh:.1f} for ci.yml")

    # Test OpenAPI sniffing
    openapi_content = """openapi: '3.0.0'
info:
  title: My API
  version: '1.0.0'
paths:
  /users:
    get:
      summary: List users
"""
    api_handler = OpenApiHandler()
    api_score = api_handler.sniff(Path("api.yaml"), openapi_content)
    k8s_score_on_api = k8s_handler.sniff(Path("api.yaml"), openapi_content)
    assert api_score > k8s_score_on_api
    print(f"✓ Content sniffing: OpenAPI={api_score:.1f} > K8s={k8s_score_on_api:.1f} for api.yaml")

    # Cleanup
    os.unlink(sql_path)

    print("\n=== All Stage 3 tests passed ===")
