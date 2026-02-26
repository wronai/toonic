# NLP/SQL Query

## Przegląd

Przeszukuj historię wymian z LLM za pomocą:
1. **NLP queries** — pytanie naturalne → SQL (local parser + LLM fallback)
2. **SQL queries** — bezpośrednie zapytania SELECT

## NLP Query — przykłady

```bash
toonic> query "show all errors from the last hour"
toonic> query "which files were fixed today?"
toonic> query "camera events with high confidence"
toonic> query "total tokens used by gemini model"
toonic> query "last 5 video analyses"
toonic> query "count errors per category"
```

Wbudowany local parser obsługuje:
- Filtry czasu: `last hour`, `today`, `last week`
- Kategorie: `video`, `code`, `logs`, `audio`
- Status: `error`, `success`
- Akcje: `fix`, `alert`, `report`
- Modele: `gemini`, `claude`, `gpt`
- Agregacje: `count`, `total`, `how many`
- Content search: `about "keyword"`

Jeśli local parser nie rozpozna zapytania — używa LLM do generowania SQL.

## SQL Query — przykłady

```bash
toonic> sql SELECT * FROM exchanges WHERE category='video' ORDER BY timestamp DESC LIMIT 10
toonic> sql SELECT model, COUNT(*), SUM(tokens_used) FROM exchanges GROUP BY model
toonic> sql SELECT action_type, AVG(confidence) FROM exchanges GROUP BY action_type
toonic> sql SELECT * FROM exchanges WHERE content LIKE '%authentication%'
toonic> sql SELECT date(timestamp, 'unixepoch') as day, COUNT(*) FROM exchanges GROUP BY day
```

## REST API

```bash
# NLP query
curl -X POST http://localhost:8900/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "show errors from last hour"}'

# SQL query
curl -X POST http://localhost:8900/api/sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM exchanges LIMIT 10"}'
```

## Bezpieczeństwo

- Tylko zapytania `SELECT` są dozwolone
- `INSERT/UPDATE/DELETE` są blokowane
- Wyniki limitowane do 50 wierszy domyślnie
