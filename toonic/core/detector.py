"""
SpecDetector — detects logic type from spec header
"""

from __future__ import annotations


class SpecDetector:
    """Wykrywa typ logiki z nagłówka pliku spec (YAML/TOON/JSON).

    Migracja z: reproducer.py SpecReproducer._detect_format()
    """

    @staticmethod
    def detect(content: str) -> str:
        """Wykryj kategorię logiki z nagłówka spec."""
        first_line = content.strip().split('\n')[0].lower()

        if '| python' in first_line or '| javascript' in first_line:
            return 'code'
        if '| markdown' in first_line or '| document' in first_line:
            return 'document'
        if '| postgresql' in first_line or '| mysql' in first_line:
            return 'database'
        if '| kubernetes' in first_line or '| terraform' in first_line:
            return 'infra'
        if '| openapi' in first_line or '| graphql' in first_line:
            return 'api'
        if '| csv' in first_line or '| excel' in first_line:
            return 'data'
        if '| dockerfile' in first_line or '| docker-compose' in first_line:
            return 'config'

        # Heurystyki na podstawie kluczy
        if 'T[' in content[:200] and 'FK→' in content[:500]:
            return 'database'
        if 'M[' in content[:200] and ('f[' in content[:500] or 'c[' in content[:500]):
            return 'code'
        if 'D[' in content[:200] and ('h1:' in content[:500] or 'h2:' in content[:500]):
            return 'document'

        return 'unknown'

    @staticmethod
    def detect_spec_format(content: str) -> str:
        """Wykryj format spec: toon, yaml, json."""
        stripped = content.strip()
        if stripped.startswith('{'):
            return 'json'
        if stripped.startswith('#') and ('M[' in stripped[:200] or 'T[' in stripped[:200]):
            return 'toon'
        return 'yaml'
