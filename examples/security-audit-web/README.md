# Security Audit (Web)

Minimalny przykład pokazujący **audyt bezpieczeństwa aplikacji webowej / API**.

W praktyce to jest połączenie:
- źródła HTTP (`https://...`) do monitoringu dostępności/odpowiedzi,
- źródła `network` do podstawowych testów sieciowych.

## Uruchomienie

Z root katalogu projektu:

```bash
python3 examples/security-audit-web/run.py
```

Skrypt robi *dry-build* konfiguracji (nie uruchamia serwera).

## Wersja 1-liner (Python)

```python
from toonic.server.quick import security_audit
security_audit("https://example.com").network("example.com").run()
```

## Wersja CLI

```bash
toonic-server --source https://example.com --source net:example.com --goal "web security audit"
```
