# 🎵 Toonic — Universal TOON Format Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-105%20passed-brightgreen.svg)](#testing)
[![Version](https://img.shields.io/badge/version-1.0.4-orange.svg)](VERSION)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](#docker)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-purple.svg)](https://openrouter.ai)

**Token-Oriented Object Notation** — kompaktowy format reprezentacji plików zoptymalizowany dla LLM.  
Toonic Server dodaje **dwukierunkowe strumieniowanie** danych między źródłami (kod, logi, kamery RTSP) a modelami LLM z pełną historią wymiany danych.

---

## 📑 Spis treści

- [Quick Start](#-quick-start)
- [Architektura](#-architektura)
- [Toonic Server](#-toonic-server)
- [CLI Shell](#-cli-shell)
- [Web UI](#-web-ui)
- [Docker](#-docker)
- [RTSP Cameras](#-rtsp-cameras)
- [Conversation History](#-conversation-history)
- [NLP/SQL Query](#-nlpsql-query)
- [LLM Router](#-llm-router)
- [Przykłady](#-przykłady)
- [API Reference](#-api-reference)
- [Testing](#-testing)
- [Dokumentacja](#-dokumentacja)
- [Roadmap](#-roadmap)

---

## 🚀 Quick Start

```bash
# 1. Instalacja
git clone https://github.com/wronai/toonic.git
cd toonic
cp .env.example .env          # ← uzupełnij LLM_API_KEY
make install-all

# 2. Konwersja pliku do TOON
toonic spec ./main.py --format toon

# 3. Start serwera z Web UI
make server
# → http://localhost:8900

# 4. Analiza projektu z LLM
make server-code

# 5. Monitoring kamery RTSP
make server-camera
```

## 🏗 Architektura

```
Sources (watchers)  →  TOON Pipeline  →  Context Accumulator  →  LLM Router  →  Actions
     ↑                                     (token budget)            ↓
     └────────── feedback ←──── History DB ←──── ActionResponse ←── LLM
                                    ↓
                              NLP/SQL Query ← User
```

| Komponent | Opis |
|-----------|------|
| **FileWatcher** | Monitoruje katalogi, konwertuje pliki do TOON |
| **LogWatcher** | Tail log files, kategoryzacja ERR/WARN/INFO |
| **StreamWatcher** | RTSP video, scene detection, keyframe extraction |
| **Accumulator** | Token budget management per kategoria |
| **LLM Router** | Routing do odpowiedniego modelu (text/code/multimodal) |
| **History DB** | SQLite log wszystkich wymian z LLM |
| **NLP/SQL Adapter** | Przeszukiwanie historii przez zapytania naturalne |

→ Pełna dokumentacja: [docs/architecture.md](docs/architecture.md)

## 🖥 Toonic Server

```bash
# Minimalny start
python -m toonic.server --source file:./src/ --goal "analyze code"

# Multi-source z kamerą
python -m toonic.server \
  --source file:./src/ \
  --source log:./logs/app.log \
  --source rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main \
  --goal "code quality + log anomalies + video monitoring" \
  --interval 30

# Z konfiguracją YAML
python -m toonic.server --config toonic-server.yaml
```

→ Dokumentacja: [docs/server.md](docs/server.md)

## 💻 CLI Shell

```bash
python -m toonic.server.client
toonic> status                           # status serwera
toonic> analyze find security issues     # trigger analizy
toonic> add ./new-project/ code          # dodaj źródło
toonic> add rtsp://cam1:554/stream video # dodaj kamerę
toonic> convert ./main.py toon           # konwersja pliku
toonic> history 10                       # ostatnie 10 wymian z LLM
toonic> query "errors from last hour"    # NLP query na historii
toonic> model google/gemini-3-flash-preview  # zmiana modelu
```

→ Dokumentacja: [docs/cli.md](docs/cli.md)

## 🌐 Web UI

Start: `make server` → otwórz http://localhost:8900

| Panel | Funkcja |
|-------|---------|
| **Live Events** | Real-time stream eventów z watcherów |
| **LLM Actions** | Odpowiedzi LLM z akcjami |
| **Sources** | Dynamiczne dodawanie/usuwanie źródeł |
| **Stats** | Tokeny, chunks, uptime, LLM calls |
| **History** | Przeglądanie historii wymian z LLM |
| **Query** | NLP/SQL wyszukiwanie w metadanych |

→ Dokumentacja: [docs/web-ui.md](docs/web-ui.md)

## 🐳 Docker

```bash
# Pełny stack: RTSP test streams + Toonic Server
cd docker/
cp ../.env.example ../.env    # uzupełnij LLM_API_KEY
docker compose up -d

# Tylko test streams (bez serwera)
make docker-streams

# Logi
make docker-logs
```

Test streams w Docker:
- `rtsp://localhost:8554/test-cam1` — 640×480 test pattern + audio
- `rtsp://localhost:8554/test-cam2` — 320×240 SMPTE bars
- `rtsp://localhost:8554/test-audio` — audio-only sine wave

→ Dokumentacja: [docs/docker.md](docs/docker.md)

## 📹 RTSP Cameras

```bash
# Real camera
python -m toonic.server \
  --source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
  --goal "security monitoring: detect movement" \
  --interval 10

# Multiple cameras
python -m toonic.server \
  --source "rtsp://admin:pass@cam1:554/stream" \
  --source "rtsp://admin:pass@cam2:554/stream" \
  --goal "multi-camera monitoring"
```

StreamWatcher automatycznie:
- Łączy się z RTSP przez OpenCV
- Wykrywa zmiany sceny (scene detection, threshold 0.4)
- Wysyła keyframes jako base64 JPEG (160×120, Q=10, ~2.5kB)
- Bez OpenCV → mock mode do testowania pipeline

## 📜 Conversation History

Każda wymiana z LLM jest zapisywana w SQLite z pełnymi metadanymi:

```python
# Programmatic access
from toonic.server.core.history import ConversationHistory

history = ConversationHistory("./toonic_history.db")
records = history.search(category="video", since="1h")
for r in records:
    print(f"[{r.timestamp}] {r.model} → {r.action_type}: {r.content[:100]}")
```

```bash
# CLI
toonic> history 20                      # last 20 exchanges
toonic> history --category video        # only video-related
toonic> history --model gemini          # only gemini model
toonic> history --action code_fix       # only code fixes
```

→ Dokumentacja: [docs/history.md](docs/history.md)

## 🔍 NLP/SQL Query

Przeszukuj historię wymian z LLM za pomocą zapytań naturalnych lub SQL:

```bash
# NLP queries (przekształcane na SQL przez LLM)
toonic> query "show all errors from the last hour"
toonic> query "which files were fixed today?"
toonic> query "camera events with high confidence"

# Direct SQL
toonic> sql SELECT * FROM exchanges WHERE category='video' ORDER BY timestamp DESC LIMIT 10
```

→ Dokumentacja: [docs/query.md](docs/query.md)

## 🔀 LLM Router

Router automatycznie kieruje zapytania do odpowiedniego modelu:

| Kategoria | Model | Routing |
|-----------|-------|---------|
| code, config, database | `code` model | Gemini / Claude |
| logs, document, data | `text` model | Gemini Flash |
| video, audio | `multimodal` model | Gemini / GPT-4o |

Konfiguracja w `.env`:
```bash
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=google/gemini-3-flash-preview
```

Lub w `toonic-server.yaml`:
```yaml
models:
  text:
    model: google/gemini-3-flash-preview
  code:
    model: google/gemini-3-flash-preview
  multimodal:
    model: google/gemini-3-flash-preview
    supports: [text, image, audio]
```

## 📂 Przykłady

| Przykład | Opis | Start |
|----------|------|-------|
| [code-analysis](examples/code-analysis/) | Analiza kodu, wykrywanie bugów | `make server-code` |
| [log-monitoring](examples/log-monitoring/) | Real-time monitoring logów | `make server-logs` |
| [video-monitoring](examples/video-monitoring/) | RTSP camera monitoring | `make server-camera` |
| [multi-source](examples/multi-source/) | Kod + logi + RTSP combined | `make server-multi` |
| [video-captioning](examples/video-captioning/) | Video captioning z LLM | [README](examples/video-captioning/) |
| [security-audit](examples/security-audit/) | Audyt bezpieczeństwa kodu | [README](examples/security-audit/) |

## 📡 API Reference

| Endpoint | Method | Opis |
|----------|--------|------|
| `/` | GET | Web UI |
| `/ws` | WS | WebSocket — live events |
| `/api/status` | GET | Server status |
| `/api/actions` | GET | Recent LLM actions |
| `/api/analyze` | POST | Trigger analysis |
| `/api/sources` | POST | Add data source |
| `/api/sources/{id}` | DELETE | Remove source |
| `/api/convert` | POST | Convert file to TOON |
| `/api/formats` | GET | List supported formats |
| `/api/history` | GET | Conversation history |
| `/api/query` | POST | NLP/SQL query on history |

→ Pełna dokumentacja: [docs/api.md](docs/api.md)

## 🧪 Testing

```bash
make test            # All tests (105+)
make test-server     # Server tests only
make test-cov        # With coverage report
```

## 📖 Dokumentacja

- [docs/architecture.md](docs/architecture.md) — Architektura systemu
- [docs/server.md](docs/server.md) — Toonic Server
- [docs/cli.md](docs/cli.md) — CLI Shell
- [docs/web-ui.md](docs/web-ui.md) — Web UI
- [docs/docker.md](docs/docker.md) — Docker setup
- [docs/api.md](docs/api.md) — REST API reference
- [docs/history.md](docs/history.md) — Conversation History
- [docs/query.md](docs/query.md) — NLP/SQL Query
- [docs/plugins.md](docs/plugins.md) — Plugin system (watchers)
- [TODO/12-toonic-server-architecture.md](TODO/12-toonic-server-architecture.md) — Architecture proposal

## 🗺 Roadmap

- [x] TOON format — 14 file type handlers
- [x] Pipeline — spec / reproduce / batch
- [x] Evidence Graph — cross-reference analysis
- [x] Server — watchers + accumulator + LLM router
- [x] Web UI — real-time events + stats
- [x] Docker — RTSP test streams
- [x] Conversation History — SQLite logging
- [x] NLP/SQL Query — search history
- [ ] gRPC transport (Phase 3)
- [ ] MCP Streamable HTTP bridge
- [ ] Rust port (tonic + prost)
- [ ] Audio VAD watcher (webrtcvad)
- [ ] Git diff watcher
- [ ] Plugin marketplace

## 📄 License

Apache-2.0 — see [LICENSE](LICENSE)
