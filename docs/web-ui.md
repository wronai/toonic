# Web UI

## Dostęp

Start serwera → otwórz http://localhost:8900

## Panele

| Panel | Funkcja |
|-------|---------|
| **Live Events** | Real-time stream z watcherów (context chunks) |
| **LLM Actions** | Odpowiedzi LLM z typem akcji i confidence |
| **Sources** | Lista źródeł + formularz dodawania nowych |
| **Stats** | Chunks, Actions, Sources, Tokens, LLM Calls, Uptime |

## Interakcje

- **Analyze Now** — trigger analizy z wybranym celem i modelem
- **Add Source** — dodaj nowe źródło danych w runtime
- **Model Select** — wybierz model: Gemini Flash, Claude Sonnet, GPT-4o

## WebSocket Events

Połączenie: `ws://localhost:8900/ws`

Typy eventów:
- `context` — nowy chunk kontekstu ze źródła
- `action` — odpowiedź LLM z akcją
- `status` — zmiana statusu serwera
- `source_added` — dodano nowe źródło
- `analysis_start` — rozpoczęto analizę
- `error` — błąd

Format:
```json
{
  "event": "action",
  "data": {
    "action_type": "report",
    "content": "Found 3 issues...",
    "model_used": "google/gemini-3-flash-preview",
    "confidence": 0.85
  },
  "timestamp": 1234567890.0
}
```
