# Security Audit (Full-Stack)

Przykład pokazuje **pełny audyt bezpieczeństwa** łączący wiele źródeł:
- kod
- logi
- network
- database
- process

Dzięki temu LLM widzi kontekst „end-to-end” i może korelować symptomy.

## Uruchomienie

Z root katalogu projektu:

```bash
python3 examples/security-audit-fullstack/run.py
```

Skrypt robi *dry-build* konfiguracji (nie startuje serwera).

## Wersja (Python)

```python
from toonic.server.quick import security_audit
(
    security_audit("./src/", "log:./auth.log")
    .network("api.example.com")
    .database("db:./app.db")
    .process("port:5432")
    .goal("comprehensive security audit")
    .run()
)
```

## Wersja CLI

```bash
toonic-server \
  --source ./src/ \
  --source log:./auth.log \
  --source net:api.example.com \
  --source db:./app.db \
  --source port:5432 \
  --goal "comprehensive security audit"
```
