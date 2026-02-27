# Security Audit (Code)

Minimalny przykład pokazujący **jednorazowy audyt bezpieczeństwa kodu** z użyciem presetów `toonic.server.quick`.

## Uruchomienie

Z root katalogu projektu:

```bash
python3 examples/security-audit-code/run.py
```

Skrypt robi *dry-build* konfiguracji (nie uruchamia serwera), więc jest bezpieczny do odpalenia.

## Wersja 1-liner (Python)

```python
from toonic.server.quick import security_audit
security_audit("./src/").run()
```

## Wersja CLI

```bash
toonic-server --source ./src/ --goal "security audit: secrets, OWASP Top 10"
```
