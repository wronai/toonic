# CLI Shell

## Uruchamianie

```bash
python -m toonic.server.client                    # localhost:8900
python -m toonic.server.client --url http://host:8900
python -m toonic.server.client --status           # one-shot status
python -m toonic.server.client --analyze "goal"   # one-shot analyze
python -m toonic.server.client --convert ./file.py --format toon
```

## Komendy

| Komenda | Opis |
|---------|------|
| `help` | Lista komend |
| `status` | Status serwera |
| `actions [N]` | Ostatnie N akcji LLM |
| `formats` | Wspierane formaty plików |
| `analyze [goal]` | Trigger analizy |
| `add <path> [category]` | Dodaj źródło danych |
| `convert <path> [format]` | Konwertuj plik do TOON/YAML/JSON |
| `model <name>` | Zmiana modelu LLM |
| `history [N]` | Ostatnie N wymian z LLM |
| `history-stats` | Statystyki historii |
| `query <pytanie>` | NLP query na historii |
| `sql <SELECT ...>` | SQL query na bazie historii |
| `quit` | Wyjście |

## Przykłady

```bash
toonic> status
toonic> analyze find all security vulnerabilities in auth module
toonic> add ./new-project/ code
toonic> add rtsp://192.168.188.146:554/h264Preview_01_main video
toonic> history 20
toonic> query "show all video analysis from last hour"
toonic> sql SELECT model, COUNT(*), AVG(duration_s) FROM exchanges GROUP BY model
toonic> model google/gemini-3-flash-preview
```
