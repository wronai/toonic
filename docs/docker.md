# Docker Setup

## Quick Start

```bash
cp .env.example .env
# Edit .env: set LLM_API_KEY=sk-or-v1-...

cd docker/
docker compose up -d
# → http://localhost:8900 (Web UI)
```

## Services

| Service | Port | Opis |
|---------|------|------|
| `rtsp-server` | 8554 (RTSP), 8888 (HLS) | MediaMTX RTSP server |
| `test-stream-video` | — | FFmpeg → test pattern 640×480 |
| `test-stream-cam2` | — | FFmpeg → SMPTE bars 320×240 |
| `test-stream-audio` | — | FFmpeg → 300Hz sine wave |
| `toonic-server` | 8900 | Toonic Server + Web UI |

## Test Streams

```bash
# Only RTSP test streams (without Toonic server)
docker compose up -d rtsp-server test-stream-video test-stream-cam2

# Verify streams
ffplay rtsp://localhost:8554/test-cam1
ffplay rtsp://localhost:8554/test-cam2
```

## Real Camera

Add in docker-compose.yml or via .env:
```bash
RTSP_CAM1=rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main
```

## Volumes

- `../examples` → `/app/examples` (read-only)
- `./test-data` → `/app/test-data` (read-only)

## Commands

```bash
docker compose up -d          # start all
docker compose logs -f        # follow logs
docker compose down           # stop
docker compose down -v        # stop + remove volumes
```
