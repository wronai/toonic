# REST API Reference

Base URL: `http://localhost:8900`

## Endpoints

### GET /
Web UI dashboard.

### WebSocket /ws
Real-time event stream. Messages are JSON:
```json
{"event": "context|action|status|error", "data": {...}, "timestamp": 1234567890.0}
```

### GET /api/status
Server status.
```json
{"running": true, "uptime_s": 120.5, "goal": "...", "sources": {...}, "total_chunks": 42}
```

### GET /api/actions?limit=20
Recent LLM actions.

### POST /api/analyze
Trigger analysis. Body: `{"goal": "...", "model": "..."}`

### POST /api/sources
Add source. Body: `{"path_or_url": "./src/", "category": "code"}`

### DELETE /api/sources/{source_id}
Remove source.

### POST /api/convert
Convert file. Body: `{"path": "./main.py", "format": "toon"}`

### GET /api/formats
List supported file formats.

### GET /api/history?limit=20&category=&model=&action_type=
Conversation history with optional filters.

### GET /api/history/stats
History statistics: total exchanges, tokens, models breakdown.

### POST /api/query
NLP query on history. Body: `{"question": "show errors from last hour"}`

### POST /api/sql
Raw SQL query. Body: `{"sql": "SELECT * FROM exchanges LIMIT 10"}`

## History Database Schema

Table: `exchanges`

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Unique exchange ID |
| timestamp | REAL | Unix epoch |
| session_id | TEXT | Server session |
| goal | TEXT | Analysis goal |
| category | TEXT | code/logs/video/... |
| model | TEXT | LLM model name |
| context_tokens | INTEGER | Tokens in context |
| action_type | TEXT | report/code_fix/alert/error |
| content | TEXT | LLM response |
| confidence | REAL | 0.0-1.0 |
| tokens_used | INTEGER | Total tokens consumed |
| duration_s | REAL | Response time |
| status | TEXT | ok/error/timeout |
