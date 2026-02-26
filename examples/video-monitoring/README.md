# Example: Video Stream Monitoring

Monitor RTSP camera streams for scene changes and anomalies.

## Quick Start (with Docker RTSP streams)

```bash
# Start test RTSP streams
cd docker/
docker compose up -d rtsp-server test-stream-video test-stream-cam2

# Start Toonic server watching the streams
python -m toonic.server \
  --source rtsp://localhost:8554/test-cam1 \
  --source rtsp://localhost:8554/test-cam2 \
  --goal "monitor video streams, detect scene changes and anomalies" \
  --interval 15

# Open http://localhost:8900 to see keyframe events
```

## With Real Cameras

```bash
python -m toonic.server \
  --source rtsp://admin:password@192.168.1.100:554/stream \
  --source rtsp://admin:password@192.168.1.101:554/stream \
  --goal "security monitoring: detect movement and unusual activity" \
  --interval 10
```

## How It Works

1. **StreamWatcher** connects to RTSP URL via OpenCV
2. Samples frames at configured interval (default: every 5s)
3. **SceneDetector** compares frames (pixel diff, threshold 0.4)
4. Keyframes are resized to 160x120, JPEG Q=10 (~2.5kB each)
5. TOON spec + base64 keyframes sent to multimodal LLM
6. LLM analyzes scene changes and reports anomalies

## Without OpenCV

If OpenCV is not installed, StreamWatcher uses a **mock mode** that generates
synthetic keyframe events — useful for testing the pipeline without real cameras.
