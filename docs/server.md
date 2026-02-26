# Toonic Server

## Uruchamianie

```bash
# Minimalne
python -m toonic.server --source file:./src/ --goal "analyze code"

# Z konfiguracją
python -m toonic.server --config toonic-server.yaml

# Multi-source
python -m toonic.server \
  --source file:./src/ \
  --source log:./logs/app.log \
  --source rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main \
  --goal "code + logs + video monitoring" \
  --interval 30
```

## Opcje CLI

| Opcja | Domyślnie | Opis |
|-------|-----------|------|
| `--source`, `-s` | — | Źródło danych (można wielokrotnie) |
| `--goal`, `-g` | "analyze..." | Cel analizy |
| `--when` | — | NLP → YAML triggers (zapisuje triggers.yaml) |
| `--triggers` | — | Ścieżka do pliku triggers.yaml |
| `--model`, `-m` | z .env | Model LLM |
| `--interval`, `-i` | 30.0 | Interwał analizy (0=one-shot) |
| `--port`, `-p` | 8900 | Port HTTP/WS |
| `--host` | 0.0.0.0 | Adres nasłuchiwania |
| `--config`, `-c` | — | Plik YAML konfiguracji |
| `--no-web` | false | Wyłącz web UI |
| `--log-level` | INFO | DEBUG/INFO/WARNING/ERROR |

## Formaty źródeł

```
file:./src/                    # katalog z kodem
log:./logs/app.log             # plik logów (tail -f)
rtsp://user:pass@host:554/path # kamera RTSP (OpenCV)
config:./config/               # pliki konfiguracyjne
data:./data/                   # pliki danych (CSV, JSON)
```

**Auto-detection kategorii:**
- `.py`, `.js`, `.go` → `code`
- `.log`, `.txt` z log: prefix → `logs`
- `rtsp://` → `video`
- `.env`, `Dockerfile` → `config`
- `.csv`, `.json` → `data`

## Konfiguracja .env

```bash
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=google/gemini-3-flash-preview
TOONIC_PORT=8900
TOONIC_INTERVAL=30
TOONIC_HISTORY_ENABLED=true
TOONIC_DB_PATH=./toonic_history.db
TOONIC_DATA_DIR=./toonic_data  # katalog dla logów i danych
```

## Data Directory

Serwer automatycznie tworzy katalog `toonic_data/` (lub `$TOONIC_DATA_DIR`):

```bash
toonic_data/
├── events.jsonl          # Wszystkie eventy (context, trigger, action, status)
├── exchanges.jsonl       # LLM exchanges (podzbiór events)
├── history.db            # SQLite z pełną historią wymian
├── server.log            # Logi serwera (console + file)
├── sources/              # Cache danych ze źródeł
└── exchanges/            # Dodatkowe dane wymian
```

**File logging:**
- Console: `stdout` (kolorowe logi)
- File: `toonic_data/server.log` (duplikat konsoli)
- Events: `toonic_data/events.jsonl` (każdy event w osobnej linii JSON)
- Exchanges: `toonic_data/exchanges.jsonl` (tylko LLM actions)

**Startup info:**
```
Toonic Server
─────────────────────────────────
Web UI:   http://0.0.0.0:8900/
API:      http://0.0.0.0:8900/api/status
WS:       ws://0.0.0.0:8900/ws
Goal:     analyze project
Sources:  3
Interval: 30.0s
Model:    default
Data:     /path/to/toonic_data/
History:  /path/to/toonic_data/history.db
Logs:     /path/to/toonic_data/events.jsonl
Triggers: 2 rule(s)
```

## Konfiguracja YAML

```yaml
# toonic-server.yaml
host: "0.0.0.0"
port: 8900
goal: "analyze project"
interval: 30.0
max_context_tokens: 100000

models:
  text:
    model: google/gemini-3-flash-preview
    max_tokens: 8192
  code:
    model: google/gemini-3-flash-preview
    max_tokens: 16384
  multimodal:
    model: google/gemini-3-flash-preview
    supports: [text, image, audio]

sources:
  - source_id: "code"
    category: code
    path_or_url: "./src/"
    watch: true
    poll_interval: 2.0
  - source_id: "logs"
    category: logs
    path_or_url: "log:./logs/app.log"
    watch: true
    poll_interval: 1.0

history_enabled: true
history_db_path: "./toonic_data/history.db"
```

## Trigger System

**NLP → YAML (--when):**
```bash
python -m toonic.server \
  --source "rtsp://admin:pass@cam:554/stream" \
  --goal "describe what you see" \
  --when "person detected for 2 seconds, if not send frame every 60s"
# → zapisuje triggers.yaml w CWD
```

**YAML file (--triggers):**
```bash
python -m toonic.server \
  --source "rtsp://cam:554/stream" \
  --triggers ./triggers.yaml
```

→ Pełna dokumentacja: [triggers.md](triggers.md)
