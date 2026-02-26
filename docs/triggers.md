# Trigger System — Event-Driven LLM Dispatch

## Przegląd

System triggerów kontroluje **kiedy** dane są wysyłane do LLM:
- **periodic** — co N sekund (niezależnie od zdarzeń)
- **on_event** — tylko gdy warunek jest spełniony (np. wykryto ruch, osobę)
- **hybrid** — na zdarzenie LUB co N sekund (co pierwsze nastąpi)

## Użycie z CLI

### `--when` — opis w języku naturalnym

```bash
# Osoba wykryta przez 1s, inaczej co 60s
python -m toonic.server \
  --source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
  --goal "describe what you see in each video frame" \
  --when "the object person will be detected for 1 second, if not send frame min. every 1 minute"

# Ruch wykryty, albo co 2 minuty
python -m toonic.server \
  --source "rtsp://cam1:554/stream" \
  --when "when motion detected, otherwise every 2 minutes"

# Błędy w logach
python -m toonic.server \
  --source "log:./app.log" \
  --when "when error occurs 5 times in 60 seconds"
```

### `--triggers` — plik YAML

```bash
python -m toonic.server \
  --source "rtsp://cam1:554/stream" \
  --triggers examples/video-captioning/triggers.yaml
```

## YAML DSL

```yaml
triggers:
  - name: person-detected
    source: video                    # video|audio|logs|code|""
    mode: on_event                   # periodic|on_event|hybrid
    events:
      - type: object                 # motion|scene_change|object|audio_level|speech|pattern|anomaly
        label: person                # for object type
        threshold: 0.3               # detection threshold
        min_duration_s: 1.0          # must persist N seconds
        min_size_pct: 5.0            # min object size as % of frame
        min_speed: 0.0               # min movement speed
    fallback:
      periodic_s: 60                 # send anyway every 60s if no event
    goal: "describe the people visible"
    cooldown_s: 5.0                  # min seconds between triggers
    priority: 8                      # 1-10

  - name: error-spike
    source: logs
    mode: on_event
    events:
      - type: pattern
        regex: "ERROR|CRITICAL"
        count_threshold: 5           # 5 occurrences
        window_s: 60                 # within 60 seconds
    goal: "analyze the error spike"
```

## Event Types

| Type | Kategoria | Opis | Kluczowe parametry |
|------|-----------|------|-------------------|
| `motion` | video | Ruch (frame diff) | `threshold`, `min_duration_s` |
| `scene_change` | video | Zmiana sceny | `threshold` |
| `object` | video | Obiekt (osoba, samochód) | `label`, `threshold`, `min_duration_s`, `min_size_pct`, `min_speed` |
| `audio_level` | audio | Poziom dźwięku | `threshold` |
| `speech` | audio | Detekcja mowy | `threshold`, `min_duration_s` |
| `pattern` | text/logs | Regex pattern | `regex`, `count_threshold`, `window_s` |
| `anomaly` | any | Odchylenie statystyczne | `threshold` (z-score) |

## NLP2YAML

Natural language → YAML trigger config via LLM:

```python
from toonic.server.triggers.nlp2yaml import NLP2YAML

nlp = NLP2YAML()
config = await nlp.generate(
    "detect person for 1 second, otherwise send frame every minute",
    source="video",
    goal="security monitoring"
)
```

Wbudowany **local parser** obsługuje częste wzorce bez LLM:
- `every N seconds/minutes` → periodic
- `when motion/person/car detected` → on_event
- `otherwise every N seconds` → fallback
- `for N seconds` → min_duration
- `N times in M seconds` → count_threshold + window
- `scene change` → scene_change event
- `speech/voice detected` → speech event

Dla złożonych opisów → automatycznie generuje YAML via LLM.

## Programmatic API

```python
from toonic.server.triggers import TriggerConfig, TriggerRule, TriggerScheduler

# From YAML
scheduler = TriggerScheduler.from_yaml(yaml_string)

# Programmatic
config = TriggerConfig(triggers=[
    TriggerRule(name="my-rule", mode="hybrid", interval_s=30,
                events=[EventCondition(type="motion", threshold=0.2)],
                fallback=FallbackConfig(periodic_s=60))
])
scheduler = TriggerScheduler(config)

# Evaluate
events = scheduler.evaluate({"scene_score": 0.5}, "video")
for event in events:
    print(f"Trigger fired: {event.rule_name} ({event.reason})")
```
