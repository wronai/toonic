# Conversation History

## Przegląd

Każda wymiana z LLM jest automatycznie logowana w SQLite z pełnymi metadanymi.
Umożliwia to:
- **Audyt** — weryfikacja poprawności każdej odpowiedzi LLM
- **Search** — przeszukiwanie wyników NLP/SQL
- **Replay** — odtworzenie sesji analizy
- **Analytics** — token usage, latencja, skuteczność modeli

## Konfiguracja

```bash
# .env
TOONIC_HISTORY_ENABLED=true
TOONIC_DB_PATH=./toonic_history.db
```

## Schema bazy

```sql
CREATE TABLE exchanges (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    session_id TEXT,
    goal TEXT,
    category TEXT,        -- code|logs|video|audio|...
    model TEXT,           -- google/gemini-3-flash-preview
    context_tokens INTEGER,
    context_preview TEXT,
    sources TEXT,          -- JSON array
    images_count INTEGER,
    action_type TEXT,      -- report|code_fix|alert|error
    content TEXT,
    confidence REAL,
    target_path TEXT,
    affected_files TEXT,   -- JSON array
    tokens_used INTEGER,
    duration_s REAL,
    status TEXT,           -- ok|error|timeout
    error_message TEXT
);
```

## Programmatic Access

```python
from toonic.server.core.history import ConversationHistory

history = ConversationHistory("./toonic_history.db")

# Recent exchanges
records = history.recent(limit=20, category="video")

# Search by text
records = history.search(query="authentication", since="1h")

# Statistics
stats = history.stats()

# Raw SQL
rows = history.execute_sql("SELECT model, COUNT(*) FROM exchanges GROUP BY model")
```

## CLI

```bash
toonic> history 20
toonic> history-stats
toonic> query "errors from last hour"
toonic> sql SELECT * FROM exchanges WHERE category='video' LIMIT 10
```

## REST API

```bash
GET  /api/history?limit=20&category=video
GET  /api/history/stats
POST /api/query   {"question": "show errors from last hour"}
POST /api/sql     {"sql": "SELECT * FROM exchanges LIMIT 10"}
```
