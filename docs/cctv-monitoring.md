# CCTV Monitoring with Toonic

Complete guide to implementing intelligent CCTV monitoring with YOLO pre-detection,
multi-frame event analysis, ROI cropping, and event-focused LLM analysis.

## Table of Contents

- [Concept](#concept)
- [How It Differs from Basic Monitoring](#how-it-differs-from-basic-monitoring)
- [Installation](#installation)
- [Command Reference](#command-reference)
- [Implementation Guide](#implementation-guide)
- [Configuration Reference](#configuration-reference)
- [Goal Prompt Engineering](#goal-prompt-engineering)
- [Trigger Design Patterns](#trigger-design-patterns)
- [Optimization](#optimization)
- [Troubleshooting](#troubleshooting)

---

## Concept

Traditional CCTV monitoring sends every frame (or scene-changed frame) to an LLM and asks
"what do you see?" — this produces **static descriptions** and wastes tokens on empty scenes.

Toonic's CCTV pipeline inverts this:

1. **Pre-detect** objects locally with YOLO (fast, cheap, runs on CPU/edge)
2. **Buffer** frames with detections, wait for event confirmation (≥2 frames, ≥1s)
3. **Crop** ROI regions around detected objects from high-resolution frames
4. **Diff** frames to highlight motion regions (red overlay)
5. **Send** only confirmed events: multi-frame sequences + ROI crops + diff to LLM
6. **Prompt** LLM for **event analysis** — actions, trajectory, classification — not scene description

This reduces LLM calls by **90%+** compared to naive frame-by-frame analysis, while
producing far more actionable intelligence.

```
┌──────────────────────────────────────────────────────────────────┐
│                    Processing Pipeline                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  RTSP Stream ──► Sample every 2s ──► YOLO detect ──► Buffer      │
│                                          │              │        │
│                                     ┌────┘         ┌────┘        │
│                                     ▼              ▼             │
│                              person: 0.87    2 frames in 3s?     │
│                              car: 0.72       → EVENT CONFIRMED   │
│                                                    │             │
│                              ┌─────────────────────┤             │
│                              ▼         ▼           ▼             │
│                          Frame 1   Frame 2     Frame 3           │
│                          (start)   (middle)    (end)             │
│                              │                     │             │
│                              ▼                     ▼             │
│                         ROI crops           Motion diff          │
│                        (bbox+pad)        (red overlay)           │
│                              │                     │             │
│                              └─────────┬───────────┘             │
│                                        ▼                         │
│                                  LLM Analysis                    │
│                           "Person entered from left,             │
│                            walking towards gate,                 │
│                            wearing dark jacket"                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## How It Differs from Basic Monitoring

| Aspect | Basic mode | Detection mode |
|--------|-----------|---------------|
| **Pre-filtering** | Scene change (pixel diff) | YOLO object detection |
| **False positive rate** | High (lighting, shadows) | Low (confirmed objects) |
| **LLM calls** | Every keyframe + heartbeat | Only confirmed events + heartbeat |
| **Images per call** | 1 frame | 3 frames + ROI crops + diff (up to 8) |
| **Resolution** | 160x120, Q=10 | 320px, Q=40 + full-res ROI crops |
| **LLM prompt** | Generic analysis | Event-focused: actions, trajectory, classification |
| **CPU cost** | Very low | Medium (YOLO inference ~50-150ms/frame) |
| **Dependencies** | `opencv-python` | `opencv-python` + `ultralytics` |

---

## Installation

```bash
# Recommended: full CCTV stack
pip install toonic[cctv]

# This installs: opencv-python, ultralytics, fastapi, uvicorn, litellm, etc.

# Minimal: detection only (no web UI)
pip install toonic[detection,llm]

# For Raspberry Pi: export YOLO to NCNN first
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='ncnn')"
```

### Environment Variables

```bash
# Required: LLM API key
export OPENROUTER_API_KEY="sk-or-..."
# Or:
export LLM_API_KEY="sk-..."
export LLM_PROVIDER="openrouter"
export LLM_MODEL="google/gemini-3-flash-preview"

# Optional
export TOONIC_PORT=8901
export TOONIC_DATA_DIR="./toonic_data"
```

---

## Command Reference

### Basic pattern

```bash
python -m toonic.server \
  --source "rtsp://user:pass@IP:554/path" \
  --goal "<event-focused description>" \
  --when "<trigger condition>"
```

### Key arguments

| Argument | Description | Example |
|----------|------------|---------|
| `--source` | RTSP URL (repeatable for multi-cam) | `rtsp://admin:pass@192.168.1.100:554/stream` |
| `--goal` | What the LLM should analyze (event-focused!) | `"detect intrusions, describe actions"` |
| `--when` | Natural language trigger condition | `"person detected for 2s, otherwise every 2min"` |
| `--triggers` | YAML file with detailed trigger rules | `triggers.yaml` |
| `--config` | Full server config YAML | `toonic-server.yaml` |
| `--interval` | Base analysis interval (seconds) | `30` |
| `--no-web` | Disable web UI | — |

---

## Implementation Guide

### Step 1: Basic person detection

```bash
python -m toonic.server \
  --source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
  --goal "CCTV: detect and describe person movement, direction, actions" \
  --when "person detected for 1 second, otherwise every 1 minute"
```

This will:
- Load YOLOv8n automatically
- Detect `person` class with confidence >0.4
- Require 2+ frames with person over ≥1s → confirm event
- Extract ROI crop of person, create motion diff
- Send multi-frame event to LLM with event-focused prompt

### Step 2: Add vehicle detection

```bash
python -m toonic.server \
  --source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
  --goal "security: detect people and vehicles, describe actions and classify events" \
  --when "person or car detected for 2 seconds, otherwise every 2 minutes"
```

### Step 3: Custom configuration (YAML)

Create `toonic-server.yaml`:

```yaml
goal: "CCTV event monitoring: describe person/vehicle actions, movement direction, classify as normal/suspicious/intrusion"
interval: 30
host: "0.0.0.0"
port: 8901

sources:
  - path_or_url: "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main"
    category: video
    options:
      # Detection settings
      detect_objects: true
      detect_model: "yolov8n.pt"
      detect_conf: 0.4
      detect_classes: "person,car,truck,motorcycle,bicycle"
      detect_resolution: 640

      # Event confirmation (anti-false-positive)
      min_event_frames: 2
      min_event_duration_s: 1.0
      event_buffer_s: 10.0

      # LLM image quality
      send_resolution: 320
      send_quality: 40

      # ROI extraction
      roi_padding: 0.15
      roi_max_crops: 4

      # Sampling
      poll_interval: 2.0
      max_silent_s: 60.0
```

Run:
```bash
python -m toonic.server --config toonic-server.yaml \
  --when "person or car detected for 1 second, otherwise every 1 minute"
```

### Step 4: Multi-camera setup

```yaml
sources:
  - path_or_url: "rtsp://admin:pass@192.168.1.100:554/ch1"
    source_id: "cam-entrance"
    category: video
    options:
      detect_classes: "person,car"
      min_event_duration_s: 1.0

  - path_or_url: "rtsp://admin:pass@192.168.1.101:554/ch1"
    source_id: "cam-parking"
    category: video
    options:
      detect_classes: "car,truck,bus"
      min_event_duration_s: 3.0

  - path_or_url: "rtsp://admin:pass@192.168.1.102:554/ch1"
    source_id: "cam-backyard"
    category: video
    options:
      detect_classes: "person,dog,cat"
      detect_conf: 0.5
```

---

## Configuration Reference

### StreamWatcher Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `detect_objects` | bool | `true` | Enable YOLO detection |
| `detect_model` | str | `yolov8n.pt` | YOLO model (.pt, NCNN, ONNX, TensorRT) |
| `detect_conf` | float | `0.4` | Confidence threshold |
| `detect_classes` | str | `person,car,truck,...` | Comma-separated class filter |
| `detect_resolution` | int | `640` | YOLO input width |
| `min_event_frames` | int | `2` | Frames needed to confirm event |
| `min_event_duration_s` | float | `1.0` | Seconds event must span |
| `event_buffer_s` | float | `10.0` | Sliding window size |
| `roi_padding` | float | `0.15` | Padding ratio around bbox |
| `roi_max_crops` | int | `4` | Max crops per emission |
| `send_resolution` | int | `320` | LLM image width |
| `send_quality` | int | `40` | JPEG quality (1-100) |
| `poll_interval` | float | `2.0` | Frame sampling interval (s) |
| `scene_threshold` | float | `0.01` | Scene change threshold (basic mode) |
| `max_silent_s` | float | `60.0` | Heartbeat interval (s) |

### YOLO Model Options

| Model | Size | CPU ms | GPU ms | Accuracy | Use case |
|-------|------|--------|--------|----------|----------|
| `yolov8n.pt` | 6.2 MB | ~120ms | ~8ms | Good | Default, edge devices |
| `yolov8s.pt` | 21.5 MB | ~200ms | ~12ms | Better | Desktop, multi-cam |
| `yolov8m.pt` | 49.7 MB | ~400ms | ~20ms | High | High-security |
| `yolov8n_ncnn_model` | ~6 MB | ~67ms (RPi5) | N/A | Good | Raspberry Pi |

### Detectable Classes (COCO dataset — YOLOv8)

Relevant for CCTV: `person`, `bicycle`, `car`, `motorcycle`, `bus`, `truck`,
`dog`, `cat`, `backpack`, `umbrella`, `handbag`, `suitcase`

---

## Goal Prompt Engineering

The `--goal` determines how the LLM analyzes events. The system automatically adds
CCTV-specific instructions when the goal contains video/monitoring keywords.

### Pattern: Event-focused (recommended)

```
"[domain]: [what to detect], [what actions to describe], [how to classify]"
```

### Examples

| Use case | Goal |
|----------|------|
| Home security | `"home CCTV: detect people at entrance, describe their actions, classify as resident/visitor/suspicious"` |
| Parking lot | `"parking monitoring: count vehicles, detect entry/exit, note illegal parking, describe vehicle types"` |
| Warehouse | `"warehouse security: detect unauthorized personnel, describe forklift movements, alert on safety violations"` |
| Retail | `"store monitoring: count customers, detect shoplifting behavior, describe movement patterns"` |
| Traffic | `"traffic monitoring: count vehicles by type, detect accidents, describe flow patterns"` |
| Wildlife | `"wildlife camera: identify animal species, describe behavior, note time and direction"` |

### Anti-patterns

| ❌ Bad | ✅ Good | Why |
|--------|---------|-----|
| `"describe what you see"` | `"describe person actions and movement"` | Static vs event-focused |
| `"analyze video"` | `"detect intrusions, classify events"` | Vague vs specific |
| `"monitor camera"` | `"track who enters, from where, wearing what"` | Generic vs actionable |

---

## Trigger Design Patterns

### Pattern 1: Person detection with fallback

```
--when "person detected for 1 second, otherwise every 1 minute"
```
→ Generates hybrid trigger: fires on person detection OR every 60s

### Pattern 2: Multi-object detection

```
--when "person or car detected for 2 seconds, otherwise every 2 minutes"
```
→ Fires when either person or car detected consistently for 2s

### Pattern 3: High-confidence only

```
--when "person detected for 3 seconds, otherwise every 5 minutes"
```
→ 3s duration = requires ~2-3 consistent frames = very low false positive rate

### YAML trigger (advanced)

```yaml
# triggers.yaml
triggers:
  - name: intrusion-detection
    mode: hybrid
    interval_s: 120.0
    source: video
    events:
      - type: object
        label: person
        threshold: 0.4
        min_duration_s: 2.0
    fallback:
      periodic_s: 120.0
    cooldown_s: 5.0
    goal: "CCTV: describe person actions, movement direction, classify event"

  - name: vehicle-detection
    mode: hybrid
    interval_s: 300.0
    source: video
    events:
      - type: object
        label: car
        threshold: 0.5
        min_duration_s: 3.0
    fallback:
      periodic_s: 300.0
    cooldown_s: 10.0
    goal: "describe vehicle type, direction, parking/passing"
```

---

## Optimization

### For Raspberry Pi / Edge

```yaml
options:
  detect_model: "yolov8n_ncnn_model"
  detect_resolution: 320
  send_resolution: 240
  send_quality: 30
  poll_interval: 3.0
  min_event_frames: 2
  max_silent_s: 180
```

### For Desktop GPU

```yaml
options:
  detect_model: "yolov8s.pt"
  detect_resolution: 640
  send_resolution: 480
  send_quality: 60
  poll_interval: 1.0
  min_event_frames: 2
```

### Reducing LLM costs

- Increase `min_event_duration_s` → fewer events
- Increase `max_silent_s` → fewer heartbeats
- Lower `send_resolution` / `send_quality` → smaller images
- Use cheaper LLM (e.g. `gemini-3-flash` vs `gpt-4o`)

### Reducing false positives

1. Raise `detect_conf` to 0.5-0.6
2. Increase `min_event_frames` to 3
3. Increase `min_event_duration_s` to 2-3s
4. Narrow `detect_classes` to only needed objects
5. Use larger YOLO model (yolov8s, yolov8m)

---

## Troubleshooting

### "ultralytics not installed — basic mode"

```bash
pip install ultralytics>=8.0
# Or: pip install toonic[detection]
```

### YOLO model download fails

```bash
# Pre-download model
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

### Low FPS on edge device

- Use NCNN export: `YOLO('yolov8n.pt').export(format='ncnn')`
- Lower `detect_resolution` to 320
- Increase `poll_interval` to 3-5s
- Use `yolov8n` (nano), not `yolov8s` (small)

### Events not firing

- Check `toonic_data/events.jsonl` for `detection_event` entries
- Lower `detect_conf` if objects aren't being detected
- Lower `min_event_frames` to 1 for testing
- Check camera connectivity: `ffprobe rtsp://...`

### LLM describes static scenes instead of events

- Use event-focused `--goal` (see Goal Prompt Engineering above)
- Ensure goal contains keywords like "detect", "actions", "events", "movement"
- The system prompt switches to CCTV mode when it detects these keywords
