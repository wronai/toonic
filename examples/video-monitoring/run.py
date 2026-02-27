#!/usr/bin/env python3
"""
CCTV/Video Monitoring — run with: python examples/video-monitoring/run.py

Before: ~25 lines of manual StreamWatcher config + YOLO options.
After:  2 lines with preset.
"""
from toonic.server.quick import cctv_monitor
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    builder = cctv_monitor("rtsp://localhost:8554/test-cam1")
    cfg = builder.build_config()
    print_config_summary(cfg, title="CCTV Monitor")
    print(f"Goal: {cfg.goal[:70]}...")
    print_to_run_hint("cctv_monitor", '"rtsp://admin:pass@192.168.1.100:554/stream"')
