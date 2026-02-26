"""
Database handlers — SQL DDL/DML
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
# Model: SQL Schema
# =============================================================================

@dataclass
class ColumnDef:
    """Definicja kolumny tabeli SQL."""
    name: str
    dtype: str
    nullable: bool = True
    constraints: List[str] = field(default_factory=list)
    references: str = ""


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
    """Logika schematu SQL — DDL, migracje, procedury."""
    source_file: str
    source_hash: str
    file_category: str = "database"

    dialect: str = "postgresql"
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
# SQL Handler
# =============================================================================

class SqlHandler(BaseHandlerMixin):
    """Handler dla SQL DDL/DML."""

    extensions = frozenset({'.sql'})
    category = 'database'
    requires = ()

    def parse(self, path: Path) -> SqlSchemaLogic:
        content = path.read_text(errors='replace')
        source_hash = self._compute_hash(path)

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
        columns = []
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
            if re.match(r'^(PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|CONSTRAINT)', part, re.IGNORECASE):
                continue

            tokens = part.split()
            if len(tokens) < 2:
                continue

            col_name = tokens[0].strip('"\'`')
            dtype = tokens[1]

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
# Rejestracja
# =============================================================================

def register_database_handlers() -> None:
    """Rejestruje handlery baz danych."""
    for handler in [SqlHandler()]:
        FormatRegistry.register(handler)
