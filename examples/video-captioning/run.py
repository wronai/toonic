#!/usr/bin/env python3
"""
Video captioning — run with: python examples/video-captioning/run.py

Before: ~20 lines manual config + multimodal model config.
After:  2 lines with quick API.
"""
from toonic.server.quick import run
from examples._helpers import print_config_summary, print_to_run_hint


if __name__ == "__main__":
    cfg = run("rtsp://cam:554/stream", goal="caption each scene change", interval=0, dry_run=True)
    print_config_summary(cfg, title="Video Captioning")
    print_to_run_hint("run", '"rtsp://cam:554/stream", goal="caption each scene change"')
