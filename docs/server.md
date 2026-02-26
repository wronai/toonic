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
log:./logs/app.log             # plik logów
rtsp://user:pass@host:554/path # kamera RTSP
config:./config/               # pliki konfiguracyjne
```

## Konfiguracja .env

```bash
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=google/gemini-3-flash-preview
TOONIC_PORT=8900
TOONIC_INTERVAL=30
TOONIC_HISTORY_ENABLED=true
TOONIC_DB_PATH=./toonic_history.db
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
```
