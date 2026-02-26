"""
Core data models — base logic classes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CodeLogicBase:
    """Bazowy model logiki kodu — adaptacja istniejącego ProjectInfo/ModuleInfo.

    Nie zastępuje models.py — rozszerza go o interfejs FileLogic.
    Istniejący ProjectInfo/ModuleInfo/ClassInfo/FunctionInfo pozostają bez zmian.
    """
    source_file: str
    source_hash: str
    file_category: str = "code"
    language: str = "python"
    lines: int = 0
    classes: List[Dict[str, Any]] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "language": self.language,
            "lines": self.lines,
            "classes": self.classes,
            "functions": self.functions,
            "imports": self.imports,
        }

    def complexity(self) -> int:
        return len(self.classes) * 3 + len(self.functions) + self.lines // 100
