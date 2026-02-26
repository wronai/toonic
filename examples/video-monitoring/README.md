# Example: Video / CCTV Monitoring

Intelligent CCTV monitoring with YOLO pre-detection, multi-frame event analysis,
ROI cropping, and event-focused LLM analysis.

## Architecture Overview

```
RTSP Camera → OpenCV capture → YOLO pre-detection → Event buffer
                                      │                    │
                                      ▼                    ▼
                              Filter classes          Confirm event
                              (person, car…)      (≥2 frames, ≥1s)
                                                        │
                                      ┌─────────────────┤
                                      ▼                 ▼
                              ROI crop (bbox)    Motion diff overlay
                                      │                 │
                                      ▼                 ▼
                              Encode JPEG ──────► Send to LLM
                              (320px, Q=40)    (event frames + ROI
                                                + diff = up to 8 imgs)
```

**Two operating modes:**

| Mode | Requirements | What it does |
|------|-------------|-------------|
| **Detection mode** | `opencv-python` + `ultralytics` | YOLO detects objects → buffers frames → confirms events → extracts ROI crops → sends multi-frame sequence + diff overlay to LLM |
| **Basic mode** | `opencv-python` only | Scene-change detection → keyframes + heartbeats → sends frames to LLM |

Detection mode activates automatically when `ultralytics` is installed.

---

## Installation

```bash
# Full CCTV setup (recommended)
pip install toonic[cctv]

# Or individual components
pip install toonic[video]        # OpenCV only (basic mode)
pip install toonic[detection]    # OpenCV + YOLO
pip install toonic[server,llm]   # Web UI + LLM
```

---

## Quick Start Examples

### 1. Basic intrusion detection (person + vehicle)

```bash
python -m toonic.server \
  --source "rtsp://admin:password@192.168.1.100:554/stream" \
  --goal "CCTV security: detect and describe intrusions, suspicious activity, vehicles" \
  --when "person or car detected for 2 seconds, otherwise check every 2 minutes"
```

**What happens:**
- YOLO detects `person` or `car` with confidence >0.4
- Waits for ≥2 frames with detections spanning ≥2s (filters transient noise)
- Extracts ROI crops of detected objects (close-up for LLM detail analysis)
- Creates motion-diff overlay (red highlights = changed pixels)
- Sends 3 event frames + ROI crops + diff to LLM → event-focused analysis
- If nothing detected for 2 minutes → sends heartbeat frame (fallback)

### 2. Event-focused monitoring (actions, not static descriptions)

```bash
python -m toonic.server \
  --source "rtsp://admin:password@192.168.1.100:554/stream" \
  --goal "describe EVENTS and ACTIONS: who entered, from where, what they're doing, vehicle movements. Classify: normal/suspicious/intrusion" \
  --when "person or vehicle detected for 1 second, otherwise every 1 minute"
```

### 3. Multi-camera property monitoring

```bash
python -m toonic.server \
  --source "rtsp://admin:pass@192.168.1.100:554/ch1" \
  --source "rtsp://admin:pass@192.168.1.101:554/ch1" \
  --source "rtsp://admin:pass@192.168.1.102:554/ch1" \
  --goal "property security: track people and vehicles across cameras, detect unauthorized entry after 22:00" \
  --when "person or car detected for 2 seconds, otherwise every 3 minutes"
```

### 4. Parking lot / garage monitoring

```bash
python -m toonic.server \
  --source "rtsp://cam:pass@192.168.1.50:554/stream" \
  --goal "parking monitoring: count vehicles, detect illegal parking, note entry/exit times and directions" \
  --when "car or truck or bus detected for 3 seconds, otherwise every 5 minutes"
```

### 5. Custom YOLO model + high-confidence detection

```bash
python -m toonic.server \
  --source "rtsp://cam@192.168.1.100:554/stream" \
  --goal "warehouse security: detect unauthorized personnel, forklift movement, safety violations" \
  --when "person detected for 2 seconds, otherwise every 2 minutes" \
  --interval 30
```

With custom detection options in `toonic-server.yaml`:

```yaml
goal: "warehouse security: detect personnel and equipment"
sources:
  - path_or_url: "rtsp://cam@192.168.1.100:554/stream"
    category: video
    options:
      detect_model: "yolov8s.pt"       # larger model, better accuracy
      detect_conf: 0.5                  # higher confidence threshold
      detect_classes: "person,forklift,truck"
      detect_resolution: 640            # YOLO input size
      min_event_frames: 3              # need 3 frames to confirm
      min_event_duration_s: 2.0        # event must last 2s
      send_resolution: 480             # higher res for LLM
      send_quality: 60                 # better JPEG quality
      roi_padding: 0.2                 # more context around ROI
      poll_interval: 1.0               # sample every 1s
      max_silent_s: 120                # heartbeat every 2min
```

### 6. Raspberry Pi / edge deployment (NCNN optimized)

```bash
# Export model for NCNN (one-time)
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='ncnn')"

# Run with NCNN model
python -m toonic.server \
  --source "rtsp://192.168.1.100:554/stream" \
  --goal "detect people and vehicles at entrance" \
  --when "person or car detected for 2 seconds, otherwise every 3 minutes"
```

With edge-optimized config in `toonic-server.yaml`:

```yaml
sources:
  - path_or_url: "rtsp://192.168.1.100:554/stream"
    category: video
    options:
      detect_model: "yolov8n_ncnn_model"  # NCNN for RPi (~7-15 FPS)
      detect_resolution: 320              # smaller = faster on RPi
      send_resolution: 240                # save bandwidth
      send_quality: 30                    # smaller images
      poll_interval: 3.0                  # less CPU usage
      min_event_frames: 2
      min_event_duration_s: 2.0
      max_silent_s: 180                   # heartbeat every 3min
```

### 7. Basic mode (without YOLO — scene change only)

```bash
python -m toonic.server \
  --source "rtsp://admin:pass@192.168.1.100:554/stream" \
  --goal "detect scene changes and describe what happened" \
  --when "scene changed, otherwise every 1 minute"
```

Force basic mode even if ultralytics is installed:

```yaml
sources:
  - path_or_url: "rtsp://192.168.1.100:554/stream"
    category: video
    options:
      detect_objects: false    # disable YOLO, use scene-change only
      scene_threshold: 0.01   # sensitivity for scene changes
      max_silent_s: 60        # heartbeat interval
```

---

## How It Works

### Detection Mode (with YOLO)

1. **StreamWatcher** connects to RTSP stream via OpenCV
2. Samples frames at `poll_interval` (default: every 2s)
3. **YOLO inference** runs on each sampled frame (in thread pool, non-blocking)
4. Detections filtered by `detect_classes` and `detect_conf`
5. Frames buffered in sliding window (`event_buffer_s`, default: 10s)
6. **Event confirmation**: requires `min_event_frames` (default: 2) with detections
   spanning `min_event_duration_s` (default: 1.0s) — filters transient false positives
7. On confirmed event:
   - **3 representative frames** selected (first, middle, last of detection window)
   - **ROI crops** extracted from high-res frames around each detected object class
   - **Motion diff overlay** generated (red highlights on changed regions)
   - All images (frames + ROI + diff) sent to multimodal LLM
8. **Heartbeat fallback**: if no detections for `max_silent_s` → emit single frame
9. LLM receives **event-focused prompt** — analyzes actions, not static appearance

### Basic Mode (OpenCV only)

1. **StreamWatcher** connects via OpenCV
2. Samples frames, computes grayscale pixel diff (scene_score)
3. Emits on `scene_score > scene_threshold` (keyframe) or periodic heartbeat
4. LLM receives keyframes for analysis

### What gets sent to LLM

In detection mode, a single event sends up to **8 images**:

| Image | Description |
|-------|------------|
| Frame 1 | Start of event (first detection) |
| Frame 2 | Middle of event |
| Frame 3 | End of event (latest detection) |
| ROI 1-4 | Close-up crops of detected objects (person, car, etc.) |
| Diff | Motion overlay: red regions = pixels that changed between frame 1→3 |

The LLM prompt instructs event-focused analysis:
- Describe **actions and movement**, not static appearance
- Note **direction, trajectory, speed** of detected objects
- **Classify events**: normal_activity, suspicious, intrusion, vehicle_entry, etc.
- Use ROI crops for **detail analysis** (clothing, vehicle type, behavior)
- Focus on **red areas** in diff overlay (motion regions)

---

## StreamWatcher Options Reference

| Option | Default | Description |
|--------|---------|------------|
| `detect_objects` | `true` | Enable YOLO detection (falls back to basic if ultralytics missing) |
| `detect_model` | `yolov8n.pt` | YOLO model path (supports .pt, NCNN, ONNX, TensorRT) |
| `detect_conf` | `0.4` | Detection confidence threshold |
| `detect_classes` | `person,car,truck,bicycle,motorcycle,bus,dog,cat` | Comma-separated class filter |
| `detect_resolution` | `640` | Frame width for YOLO inference |
| `min_event_frames` | `2` | Minimum frames with detections to confirm event |
| `min_event_duration_s` | `1.0` | Minimum event duration in seconds |
| `event_buffer_s` | `10.0` | Sliding window buffer duration |
| `roi_padding` | `0.15` | Padding ratio around ROI bounding boxes |
| `roi_max_crops` | `4` | Maximum ROI crops per emission |
| `send_resolution` | `320` | Frame width for LLM images |
| `send_quality` | `40` | JPEG quality for LLM images (1-100) |
| `poll_interval` | `2.0` | Seconds between sampled frames |
| `scene_threshold` | `0.01` | Scene change threshold for basic mode |
| `max_silent_s` | `60.0` | Max seconds without emission (heartbeat interval) |

---

## Tips for Effective CCTV Monitoring

### Writing good `--goal` prompts

❌ **Bad** (static description):
```
"describe what you see in each video frame"
```

✅ **Good** (event-focused):
```
"CCTV security: detect intrusions, describe person actions and movement direction, classify events as normal/suspicious/intrusion"
```

✅ **Better** (domain-specific):
```
"property entrance monitoring: track who enters/exits, note vehicle plates if visible, detect unauthorized access after 22:00, alert on suspicious loitering >30s"
```

### Writing good `--when` triggers

❌ **Too sensitive** (fires on every frame):
```
"any movement detected"
```

✅ **Robust** (confirmed events only):
```
"person or car detected for 2 seconds, otherwise every 2 minutes"
```

✅ **Multi-condition**:
```
"person detected for 1 second or vehicle detected for 3 seconds, otherwise every 5 minutes"
```

### Optimizing for different hardware

| Platform | Model | detect_resolution | poll_interval | Expected FPS |
|----------|-------|-------------------|---------------|-------------|
| Desktop GPU | yolov8s.pt | 640 | 1.0 | 30+ |
| Desktop CPU | yolov8n.pt | 640 | 2.0 | 10-15 |
| RPi 5 | yolov8n (NCNN) | 320 | 3.0 | 7-15 |
| RPi 4 | yolov8n (NCNN) | 320 | 5.0 | 3-7 |

### Reducing false positives

1. **Increase `min_event_frames`** to 3 — requires more consistent detection
2. **Increase `min_event_duration_s`** to 2-3s — filters momentary triggers
3. **Raise `detect_conf`** to 0.5-0.6 — only high-confidence detections
4. **Narrow `detect_classes`** — only classes you care about
5. **Use a larger model** (yolov8s, yolov8m) for better accuracy

---

## Without OpenCV

If OpenCV is not installed, StreamWatcher uses a **mock mode** that generates
synthetic keyframe events — useful for testing the pipeline without real cameras.
