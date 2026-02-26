"""
Data handlers — CSV/TSV, JSON data
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from toonic.core.base import BaseHandlerMixin
from toonic.core.registry import FormatRegistry


# =============================================================================
# Modele logiki — Dane
# =============================================================================

@dataclass
class ColumnSpec:
    """Specyfikacja kolumny tabeli."""
    name: str
    dtype: str = "string"
    nullable: bool = True
    sample_values: List[str] = field(default_factory=list)
    unique_ratio: float = 0.0


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

    root_type: str = "object"
    keys: List[Dict[str, str]] = field(default_factory=list)
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
# CSV Handler
# =============================================================================

class CsvHandler(BaseHandlerMixin):
    """Handler dla CSV/TSV."""

    extensions = frozenset({'.csv', '.tsv'})
    category = 'data'
    requires = ()

    def parse(self, path: Path) -> TableLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

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

        has_header = csv.Sniffer().has_header(sniffer_sample) if sniffer_sample else True
        headers = rows_data[0] if has_header else [f"col_{i}" for i in range(len(rows_data[0]))]
        data_rows = rows_data[1:] if has_header else rows_data

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
        non_empty = [v for v in values if v.strip()]
        if not non_empty:
            return "null"
        if all(re.match(r'^-?\d+$', v) for v in non_empty[:20]):
            return "int"
        if all(re.match(r'^-?\d*\.?\d+$', v) for v in non_empty[:20]):
            return "float"
        if all(v.lower() in ('true', 'false', '0', '1', 'yes', 'no') for v in non_empty[:20]):
            return "bool"
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
    """Handler dla plików z danymi JSON (nie JSON Schema, nie package.json)."""

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
        score = 0.0
        stripped = content.strip()
        if stripped.startswith('{') or stripped.startswith('['):
            score += 0.3
        name = path.name.lower()
        config_names = {'package.json', 'tsconfig.json', 'tslint.json', 'eslint.json',
                       'composer.json', '.babelrc', 'jest.config.json'}
        if name in config_names:
            score -= 0.5
        return max(score, 0.0)


# =============================================================================
# Rejestracja
# =============================================================================

def register_data_handlers() -> None:
    """Rejestruje handlery danych."""
    for handler in [CsvHandler(), JsonDataHandler()]:
        FormatRegistry.register(handler)
