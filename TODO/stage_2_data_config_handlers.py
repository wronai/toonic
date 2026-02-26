"""
Toonic — Etap 2: Handlery danych i konfiguracji
================================================

Obsługa: CSV/TSV, JSON-data, TOML, Dockerfile, .env, pyproject.toml, docker-compose.
Każdy plik → odpowiednia Logic → TOON spec → reprodukcja.

Migrowane funkcje z code2logic:
- generators.py CSVGenerator → CsvHandler.to_spec()
- generators.py JSONGenerator → JsonDataHandler.to_spec()
- file_formats.py format detection → handler.sniff()
- plan v2.0 Sprint 1 (dane strukturalne) → stage 2
- plan v2.0 Sprint 2 (konfiguracja) → stage 2
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from stage_0_foundation import BaseHandlerMixin, FileLogic, FormatRegistry


# =============================================================================
# Modele logiki — Dane
# =============================================================================

@dataclass
class ColumnSpec:
    """Specyfikacja kolumny tabeli."""
    name: str
    dtype: str = "string"       # string | int | float | bool | date | null
    nullable: bool = True
    sample_values: List[str] = field(default_factory=list)  # max 3 przykłady
    unique_ratio: float = 0.0   # 0.0 - 1.0


@dataclass
class TableLogic:
    """Logika danych tabelarycznych — CSV, Excel, SQL wyniki."""
    source_file: str
    source_hash: str
    file_category: str = "data"

    rows: int = 0
    columns: List[ColumnSpec] = field(default_factory=list)
    delimiter: str = ","
    has_header: bool = True
    encoding: str = "utf-8"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "rows": self.rows,
            "columns": [
                {"name": c.name, "dtype": c.dtype, "nullable": c.nullable,
                 "samples": c.sample_values[:3]}
                for c in self.columns
            ],
            "delimiter": self.delimiter,
            "has_header": self.has_header,
        }

    def complexity(self) -> int:
        return len(self.columns) * 2 + self.rows // 1000


@dataclass
class JsonSchemaLogic:
    """Logika danych JSON — schemat i struktura."""
    source_file: str
    source_hash: str
    file_category: str = "data"

    root_type: str = "object"   # object | array | primitive
    keys: List[Dict[str, str]] = field(default_factory=list)  # [{name, type, nested}]
    depth: int = 0
    array_lengths: Dict[str, int] = field(default_factory=dict)
    total_keys: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "root_type": self.root_type,
            "keys": self.keys,
            "depth": self.depth,
            "total_keys": self.total_keys,
        }

    def complexity(self) -> int:
        return self.total_keys + self.depth * 3


# =============================================================================
# Modele logiki — Konfiguracja
# =============================================================================

@dataclass
class ConfigEntry:
    """Pojedynczy wpis konfiguracyjny."""
    key: str
    value_type: str = "string"  # string | int | bool | list | dict
    category: str = ""          # env, build, runtime, network, security
    sensitive: bool = False     # hasła, klucze API
    description: str = ""


@dataclass
class ConfigLogic:
    """Logika pliku konfiguracyjnego."""
    source_file: str
    source_hash: str
    file_category: str = "config"

    config_type: str = "env"    # env | dockerfile | docker-compose | pyproject | toml
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
# CSV Handler
# =============================================================================

class CsvHandler(BaseHandlerMixin):
    """Handler dla CSV/TSV.

    Migracja z code2logic:
    - generators.py CSVGenerator → to_spec()
    - plan v2.0 Sprint 1 csv_plugin.py → cały handler
    """

    extensions = frozenset({'.csv', '.tsv'})
    category = 'data'
    requires = ()

    def parse(self, path: Path) -> TableLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        # Wykryj delimiter
        sniffer_sample = content[:4096]
        try:
            dialect = csv.Sniffer().sniff(sniffer_sample)
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = '\t' if path.suffix == '.tsv' else ','

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows_data = list(reader)

        if not rows_data:
            return TableLogic(source_file=path.name, source_hash=source_hash)

        # Nagłówki
        has_header = csv.Sniffer().has_header(sniffer_sample) if sniffer_sample else True
        headers = rows_data[0] if has_header else [f"col_{i}" for i in range(len(rows_data[0]))]
        data_rows = rows_data[1:] if has_header else rows_data

        # Analiza kolumn
        columns = []
        for i, name in enumerate(headers):
            col_values = [row[i] for row in data_rows if i < len(row)]
            dtype = self._infer_dtype(col_values[:100])
            samples = [v for v in col_values[:5] if v][:3]
            nullable = any(v == '' or v is None for v in col_values[:100])
            unique_count = len(set(col_values[:1000]))
            total = min(len(col_values), 1000)
            unique_ratio = unique_count / total if total > 0 else 0

            columns.append(ColumnSpec(
                name=name,
                dtype=dtype,
                nullable=nullable,
                sample_values=samples,
                unique_ratio=round(unique_ratio, 2),
            ))

        return TableLogic(
            source_file=path.name,
            source_hash=source_hash,
            rows=len(data_rows),
            columns=columns,
            delimiter=delimiter,
            has_header=has_header,
        )

    def _infer_dtype(self, values: List[str]) -> str:
        """Wnioskuj typ kolumny z próbki wartości."""
        non_empty = [v for v in values if v.strip()]
        if not non_empty:
            return "null"

        # Sprawdź int
        if all(re.match(r'^-?\d+$', v) for v in non_empty[:20]):
            return "int"
        # Sprawdź float
        if all(re.match(r'^-?\d*\.?\d+$', v) for v in non_empty[:20]):
            return "float"
        # Sprawdź bool
        if all(v.lower() in ('true', 'false', '0', '1', 'yes', 'no') for v in non_empty[:20]):
            return "bool"
        # Sprawdź date
        if all(re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}', v) for v in non_empty[:20]):
            return "date"
        return "string"

    def to_spec(self, logic: TableLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            return self._to_toon(logic)
        elif fmt == 'yaml':
            return self._to_yaml(logic)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def _to_toon(self, t: TableLogic) -> str:
        """
        # data.csv | csv | 1250 rows | 8 cols
        C[8]:
          id:int PK | name:str | email:str UNIQUE | age:int? | ...
        sample[3]:
          1,Alice,alice@ex.com,30,...
        """
        lines = [f"# {t.source_file} | csv | {t.rows} rows | {len(t.columns)} cols"]
        lines.append(f"C[{len(t.columns)}]:")
        col_parts = []
        for c in t.columns:
            part = f"{c.name}:{c.dtype}"
            if not c.nullable:
                part += " NN"
            if c.unique_ratio > 0.95:
                part += " UNIQUE"
            col_parts.append(part)
        lines.append("  " + ", ".join(col_parts))

        # Próbki
        max_samples = min(3, min(len(c.sample_values) for c in t.columns) if t.columns else 0)
        if max_samples > 0:
            lines.append(f"sample[{max_samples}]:")
            for i in range(max_samples):
                row = [c.sample_values[i] if i < len(c.sample_values) else "" for c in t.columns]
                lines.append("  " + t.delimiter.join(row))

        return '\n'.join(lines)

    def _to_yaml(self, t: TableLogic) -> str:
        lines = [f"# {t.source_file} | csv | {t.rows} rows"]
        lines.append(f"rows: {t.rows}")
        lines.append(f"delimiter: '{t.delimiter}'")
        lines.append("columns:")
        for c in t.columns:
            lines.append(f"  - name: {c.name}")
            lines.append(f"    type: {c.dtype}")
            if c.sample_values:
                lines.append(f"    samples: {c.sample_values[:3]}")
        return '\n'.join(lines)

    def reproduce(self, logic: TableLogic, client: Any = None, target_fmt: str | None = None) -> str:
        """Reprodukuje CSV z headerem i placeholder danymi."""
        header = logic.delimiter.join(c.name for c in logic.columns)
        rows = [header]
        for i in range(min(5, logic.rows)):
            row = []
            for c in logic.columns:
                if i < len(c.sample_values):
                    row.append(c.sample_values[i])
                else:
                    row.append(f"sample_{c.name}_{i}")
            rows.append(logic.delimiter.join(row))
        return '\n'.join(rows)

    def sniff(self, path: Path, content: str) -> float:
        score = 0.0
        # Sprawdź czy wygląda na CSV
        first_lines = content.split('\n')[:5]
        if first_lines:
            delimiters = [line.count(',') for line in first_lines]
            if delimiters and all(d == delimiters[0] and d > 0 for d in delimiters):
                score += 0.6
            tab_counts = [line.count('\t') for line in first_lines]
            if tab_counts and all(t == tab_counts[0] and t > 0 for t in tab_counts):
                score += 0.6
        return min(score, 1.0)


# =============================================================================
# JSON Data Handler
# =============================================================================

class JsonDataHandler(BaseHandlerMixin):
    """Handler dla plików z danymi JSON (nie JSON Schema, nie package.json).

    Migracja z code2logic:
    - generators.py JSONGenerator → to_spec()
    """

    extensions = frozenset({'.json'})
    category = 'data'
    requires = ()

    def parse(self, path: Path) -> JsonSchemaLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return JsonSchemaLogic(source_file=path.name, source_hash=source_hash)

        root_type = type(data).__name__
        if isinstance(data, dict):
            root_type = "object"
        elif isinstance(data, list):
            root_type = "array"

        keys = []
        depth = self._compute_depth(data)
        total_keys = self._count_keys(data)

        if isinstance(data, dict):
            for k, v in list(data.items())[:50]:
                keys.append({
                    "name": str(k),
                    "type": type(v).__name__,
                    "nested": str(isinstance(v, (dict, list))),
                })

        return JsonSchemaLogic(
            source_file=path.name,
            source_hash=source_hash,
            root_type=root_type,
            keys=keys,
            depth=depth,
            total_keys=total_keys,
        )

    def _compute_depth(self, obj: Any, current: int = 0) -> int:
        if isinstance(obj, dict):
            if not obj:
                return current
            return max(self._compute_depth(v, current + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return current
            return max(self._compute_depth(v, current + 1) for v in obj[:10])
        return current

    def _count_keys(self, obj: Any) -> int:
        if isinstance(obj, dict):
            return len(obj) + sum(self._count_keys(v) for v in obj.values())
        elif isinstance(obj, list):
            return sum(self._count_keys(v) for v in obj[:100])
        return 0

    def to_spec(self, logic: JsonSchemaLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            lines = [f"# {logic.source_file} | json-data | {logic.total_keys} keys | depth:{logic.depth}"]
            lines.append(f"root: {logic.root_type}")
            if logic.keys:
                lines.append(f"K[{len(logic.keys)}]:")
                for k in logic.keys:
                    nested = " →nested" if k.get("nested") == "True" else ""
                    lines.append(f"  {k['name']}:{k['type']}{nested}")
            return '\n'.join(lines)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def reproduce(self, logic: JsonSchemaLogic, client: Any = None, target_fmt: str | None = None) -> str:
        obj = {}
        for k in logic.keys:
            if k["type"] == "str":
                obj[k["name"]] = f"sample_{k['name']}"
            elif k["type"] == "int":
                obj[k["name"]] = 0
            elif k["type"] == "list":
                obj[k["name"]] = []
            elif k["type"] == "dict":
                obj[k["name"]] = {}
            else:
                obj[k["name"]] = None
        return json.dumps(obj, indent=2, ensure_ascii=False)

    def sniff(self, path: Path, content: str) -> float:
        """Wykryj pliki z danymi JSON (nie package.json, tsconfig.json itp.)."""
        score = 0.0
        stripped = content.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            score += 0.3
        # Negatywne sygnały — to konfiguracja, nie dane
        name = path.name.lower()
        config_names = {'package.json', 'tsconfig.json', 'tslint.json', 'eslint.json',
                       'composer.json', '.babelrc', 'jest.config.json'}
        if name in config_names:
            score -= 0.5
        return max(score, 0.0)


# =============================================================================
# Dockerfile Handler
# =============================================================================

class DockerfileHandler(BaseHandlerMixin):
    """Handler dla Dockerfile."""

    extensions = frozenset(set())  # Brak rozszerzenia — wykrywanie po nazwie
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
            # Grupuj po kategoriach
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
        # Sprawdź wzorzec KEY=VALUE
        env_lines = [l for l in content.split('\n')[:20]
                     if l.strip() and not l.startswith('#')]
        if env_lines and all('=' in l for l in env_lines):
            score += 0.3
        return min(score, 1.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_data_config_handlers() -> None:
    """Rejestruje handlery danych i konfiguracji."""
    for handler in [
        CsvHandler(),
        JsonDataHandler(),
        DockerfileHandler(),
        EnvHandler(),
    ]:
        FormatRegistry.register(handler)


# =============================================================================
# Testy
# =============================================================================

if __name__ == '__main__':
    import tempfile, os

    print("=== Toonic Stage 2: Data & Config Handlers Tests ===\n")

    FormatRegistry.reset()
    register_data_config_handlers()

    # Test CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("id,name,email,age\n1,Alice,alice@ex.com,30\n2,Bob,bob@ex.com,25\n3,Carol,carol@ex.com,35\n")
        csv_path = Path(f.name)
        f.flush()

    csv_handler = FormatRegistry.resolve(csv_path)
    assert isinstance(csv_handler, CsvHandler)
    csv_logic = csv_handler.parse(csv_path)
    assert csv_logic.rows == 3
    assert len(csv_logic.columns) == 4
    assert csv_logic.columns[0].dtype == 'int'
    assert csv_logic.columns[1].dtype == 'string'
    toon = csv_handler.to_spec(csv_logic, 'toon')
    print(f"✓ CSV: {csv_logic.rows} rows, {len(csv_logic.columns)} cols")
    print(f"  TOON:\n{toon}\n")

    # Test .env
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DB_HOST=localhost\nDB_PORT=5432\nAPI_SECRET_KEY=mysecret123\nDEBUG=true\n")
        env_path = Path(f.name)
        f.flush()

    env_handler = FormatRegistry.resolve(env_path)
    assert isinstance(env_handler, EnvHandler)
    env_logic = env_handler.parse(env_path)
    assert len(env_logic.entries) == 4
    secret_entry = [e for e in env_logic.entries if e.key == 'API_SECRET_KEY'][0]
    assert secret_entry.sensitive is True
    assert secret_entry.description == '***'
    toon = env_handler.to_spec(env_logic, 'toon')
    print(f"✓ Env: {len(env_logic.entries)} vars, sensitive detected")
    print(f"  TOON:\n{toon}\n")

    # Test JSON data
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"users": [{"id": 1, "name": "Alice"}], "total": 100}, f)
        json_path = Path(f.name)
        f.flush()

    json_handler = FormatRegistry.resolve(json_path)
    assert isinstance(json_handler, JsonDataHandler)
    json_logic = json_handler.parse(json_path)
    assert json_logic.root_type == 'object'
    assert json_logic.total_keys > 0
    toon = json_handler.to_spec(json_logic, 'toon')
    print(f"✓ JSON: {json_logic.total_keys} keys, depth:{json_logic.depth}")
    print(f"  TOON:\n{toon}\n")

    # Cleanup
    for p in [csv_path, env_path, json_path]:
        os.unlink(p)

    print("=== All Stage 2 tests passed ===")
