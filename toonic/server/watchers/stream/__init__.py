"""Stream watcher package - video stream monitoring with YOLO detection."""
from __future__ import annotations

# Data models
from toonic.server.watchers.stream.models import Detection, FrameRecord

# Main watcher (backward compatible)
from toonic.server.watchers.stream.watcher import StreamWatcher

__all__ = [
    "Detection",
    "FrameRecord", 
    "StreamWatcher",
]
