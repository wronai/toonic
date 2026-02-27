# Security Monitoring (Continuous)

Przykład pokazuje **ciągły monitoring bezpieczeństwa** (kod + logi) z cykliczną analizą.

## Uruchomienie

Z root katalogu projektu:

```bash
python3 examples/security-audit-continuous/run.py
```

Skrypt robi *dry-build* konfiguracji.

## Wersja (Python)

```python
from toonic.server.quick import security_audit
(
    security_audit("./src/", "log:./app.log")
    .interval(300)
    .goal("continuous security monitoring")
    .run()
)
```

## Wersja CLI

```bash
toonic-server --source ./src/ --source log:./app.log --interval 300 --goal "continuous security monitoring"
```
