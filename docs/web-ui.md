# Web UI

## Dostęp

Start serwera → otwórz http://localhost:8900

## Nowy Tabbed Layout

Web UI został przeprojektowany z 6 zakładkami:

| Tab | Funkcja |
|-----|---------|
| **Events** | Live event stream (context, trigger, action, error) z filtrowaniem |
| **LLM Actions** | Przeglądarka wymian z LLM (expandable, pełne metadata) |
| **History** | SQLite conversation history + NLP query interface |
| **Triggers** | Trigger rules config + runtime stats (event_count, periodic_count) |
| **Sources** | Active sources + dynamiczne dodawanie/usuwanie |
| **Overview** | Server stats: chunks, actions, events, tokens, uptime, data_dir |

## Features

**Events Tab:**
- Live stream wszystkich eventów przez WebSocket
- Filtrowanie: All / Context / Triggers / Actions / Status / Errors
- Click to expand — pokaż pełny content
- Auto-scroll do najnowszych
- Clear button

**LLM Actions Tab:**
- Przeglądarka wszystkich wymian z LLM
- Metadata: action_type, model_used, duration_s, timestamp
- Expandable content (click to show full response)
- Manual trigger: Goal input + Model select + Analyze Now button

**History Tab:**
- Browse SQLite conversation history
- Filters: category, model, action_type
- NLP Query interface: `"errors from last hour"` → SQL → results
- Expandable exchanges z pełnymi metadanymi

**Triggers Tab:**
- Display trigger rules z konfiguracji
- Runtime stats per rule: event_count, periodic_count, last_triggered
- Mode, interval, cooldown, fallback info
- Event conditions z thresholds

**Sources Tab:**
- Lista aktywnych źródeł (source_id + watcher type)
- Add Source form: path/URL + category select
- Dynamic add/remove w runtime

**Overview Tab:**
- Server stats grid: chunks, actions, events, sources, tokens, LLM calls, trigger rules, uptime
- Data directory path display
- Auto-refresh co 5s

## WebSocket Events

Połączenie: `ws://localhost:8900/ws`

**Typy eventów:**
- `context` — nowy chunk kontekstu ze źródła
- `trigger` — trigger fired (rule, reason, detections, goal)
- `action` — odpowiedź LLM z akcją
- `analysis_start` — rozpoczęto analizę (context_tokens, sources)
- `status` — zmiana statusu serwera
- `source_added` — dodano nowe źródło
- `error` — błąd

**Format eventów:**

```json
// Context event
{
  "event": "context",
  "data": {
    "source_id": "video:rtsp://...",
    "category": "video",
    "toon_spec": "# video | 160x120 | ...",
    "metadata": {"fps": 6.0}
  },
  "timestamp": 1772108742.92
}

// Trigger event
{
  "event": "trigger",
  "data": {
    "rule": "object-person-hybrid",
    "reason": "periodic",
    "detections": [],
    "goal": "describe what you see"
  },
  "timestamp": 1772108742.92
}

// Action event
{
  "event": "action",
  "data": {
    "action_type": "report",
    "content": "The frame shows...",
    "model_used": "google/gemini-3-flash-preview",
    "confidence": 0.7,
    "duration_s": 6.7
  },
  "timestamp": 1772108749.22
}
```

## REST API Endpoints

**Nowe endpointy:**

| Endpoint | Method | Opis |
|----------|--------|------|
| `/api/events` | GET | Event log (limit, event_type filter) |
| `/api/triggers` | GET | Trigger config + runtime stats |
| `/api/data-dir` | GET | List files in data directory |
| `/api/history/stats` | GET | History statistics |
| `/api/sql` | POST | Direct SQL query on history |

**Przykłady:**

```bash
# Get last 50 events
curl http://localhost:8900/api/events?limit=50

# Get only trigger events
curl http://localhost:8900/api/events?event_type=trigger

# Get trigger config + stats
curl http://localhost:8900/api/triggers

# List data directory files
curl http://localhost:8900/api/data-dir

# NLP query on history
curl -X POST http://localhost:8900/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "errors from last hour"}'

# Direct SQL query
curl -X POST http://localhost:8900/api/sql \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM exchanges WHERE category='video' LIMIT 10"}'
```

## UI Styling

- Dark theme (background: #0f1117)
- Color-coded events:
  - Context: blue (#3b82f6)
  - Triggers: orange (#f59e0b)
  - Actions: green (#10b981)
  - Errors: red (#ef4444)
  - Status: purple (#8b5cf6)
- Monospace font dla event content
- Hover effects + expandable cards
- Auto-scroll w event stream
- Responsive layout (mobile-friendly)

## JavaScript API

**WebSocket connection:**
```javascript
const ws = new WebSocket('ws://localhost:8900/ws');

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  console.log(msg.event, msg.data);
};

// Send command
ws.send(JSON.stringify({
  command: 'analyze',
  goal: 'find bugs',
  model: 'google/gemini-3-flash-preview'
}));
```

**Fetch API:**
```javascript
// Get events
const events = await fetch('/api/events?limit=100').then(r => r.json());

// Trigger analysis
const result = await fetch('/api/analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({goal: 'analyze code', model: ''})
}).then(r => r.json());

// Add source
await fetch('/api/sources', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    path_or_url: 'rtsp://cam:554/stream',
    category: 'video'
  })
});
```
