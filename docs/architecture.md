# Architektura Toonic Server

## Diagram przepływu danych

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TOONIC SERVER                               │
│                                                                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
│  │FileWatcher │ │LogWatcher  │ │StreamWatch │ │PluginWatch │      │
│  │(code,cfg)  │ │(tail logs) │ │(RTSP/video)│ │(MQTT,HTTP) │      │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘      │
│        │               │               │               │            │
│        ▼               ▼               ▼               ▼            │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              TOON Conversion Pipeline                     │      │
│  │  FileHandler.parse() → FileLogic → to_spec('toon')       │      │
│  └────────────────────────┬─────────────────────────────────┘      │
│                           │                                         │
│                           ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              Context Accumulator                          │      │
│  │  Token budget: code=40% logs=15% video=15% audio=10%     │      │
│  │  Priority queue → eviction LRU                            │      │
│  └────────────────────────┬─────────────────────────────────┘      │
│                           │                                         │
│                           ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              LLM Router                                   │      │
│  │  code → gemini-3-flash │ video → gemini-3-flash (multi)  │      │
│  │  logs → gemini-3-flash │ audio → gemini-3-flash (multi)  │      │
│  └──────┬───────────────────────────────┬───────────────────┘      │
│         │                               │                           │
│         ▼                               ▼                           │
│  ┌──────────────┐              ┌──────────────────┐                │
│  │History DB    │              │Action Executor    │                │
│  │(SQLite)      │              │code_fix / report  │                │
│  └──────┬───────┘              └──────────────────┘                │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              NLP/SQL Query Adapter                        │      │
│  │  "show errors last hour" → SELECT * FROM exchanges ...   │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ── External APIs ──────────────────────────────────────────────   │
│  REST + WebSocket (FastAPI)  │  CLI Shell  │  Web UI               │
└─────────────────────────────────────────────────────────────────────┘
```

## Komponenty

### Source Watchers
Każdy watcher to niezależny async task, który emituje `ContextChunk`:

| Watcher | Trigger | Output |
|---------|---------|--------|
| **FileWatcher** | inotify/poll | TOON spec kodu |
| **LogWatcher** | tail -f | TOON z kategoryzacją ERR/WARN/INFO |
| **StreamWatcher** | RTSP frames | base64 JPEG keyframes + TOON metadata |

### Context Accumulator
Zarządza budżetem tokenów (domyślnie 100k):
- Priorytetyzacja per kategoria (code 40%, logs 15%, video 15%)
- LRU eviction — najstarsze chunki usuwane pierwsze
- Delta mode — po pierwszym snapshot, tylko zmiany

### LLM Router
Routing zapytań do modeli per typ danych:
- `code/config/database` → model `code`
- `logs/document/data` → model `text`
- `video/audio` → model `multimodal` (z base64 obrazami)

### Conversation History
SQLite z pełnymi metadanymi każdej wymiany:
- Request: goal, category, model, context_tokens, images
- Response: action_type, content, confidence, affected_files
- Metrics: tokens_used, duration_s, status

### NLP/SQL Query
Dwa tryby przeszukiwania historii:
1. **NLP** — pytanie naturalne → SQL (generowane przez LLM lub local parser)
2. **SQL** — bezpośrednie zapytanie SELECT na tabeli `exchanges`

## Dwukierunkowy przepływ danych

```
User/Watcher → Context → LLM → Action → User
     ↑                            │
     └──── feedback ──────────────┘

User → NLP Query → History DB → Results → User
```

Każda wymiana z LLM jest logowana w History DB, co umożliwia:
- Audyt poprawności działania systemu
- Przeszukiwanie wyników analizy
- Replay sesji analizy
- Analitykę: tokeny, latencja, skuteczność modeli
