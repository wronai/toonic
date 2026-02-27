#!/usr/bin/env python3
"""
CCTV/Video Monitoring — run with: python examples/video-monitoring/run.py

Before: ~25 lines of manual StreamWatcher config + YOLO options.
After:  2 lines with preset.
"""
from toonic.server.quick import cctv_monitor

if __name__ == "__main__":
    builder = cctv_monitor("rtsp://localhost:8554/test-cam1")
    cfg = builder.build_config()
    print(f"CCTV Monitor: {len(cfg.sources)} sources")
    print(f"Goal: {cfg.goal[:70]}...")
    for s in cfg.sources:
        print(f"  [{s.category}] {s.path_or_url}")
    print("\nTo run with real camera:")
    print('  from toonic.server.quick import cctv_monitor')
    print('  cctv_monitor("rtsp://admin:pass@192.168.1.100:554/stream").run()')
