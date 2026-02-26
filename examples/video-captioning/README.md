# Example: Video Captioning

Analyze RTSP camera streams and generate captions/descriptions using multimodal LLM.

## Quick Start

```bash
# With real camera
python -m toonic.server \
  --source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
  --goal "describe what you see in each video frame, generate captions for the video stream" \
  --model google/gemini-3-flash-preview \
  --interval 15

# With Docker test stream
python -m toonic.server \
  --source rtsp://localhost:8554/test-cam1 \
  --goal "describe the video frames, caption each scene change" \
  --interval 10
```

## How It Works

1. **StreamWatcher** captures RTSP frames via OpenCV
2. Scene change detection identifies keyframes (threshold 0.4)
3. Keyframes resized to 160×120, JPEG Q=10 (~2.5kB)
4. Base64 images + TOON metadata sent to multimodal LLM
5. LLM generates captions/descriptions
6. All exchanges logged to history DB
7. Search captions via NLP: `toonic> query "scenes with people"`

## Querying Captions

```bash
python -m toonic.server.client
toonic> history 20                      # see recent captions
toonic> query "video analyses with high confidence"
toonic> sql SELECT content FROM exchanges WHERE category='video' ORDER BY timestamp DESC LIMIT 5
```

## Docker Compose

```bash
cd docker/
docker compose up -d
# Toonic server automatically watches test-cam1
# Open http://localhost:8900 for live captioning events
```
