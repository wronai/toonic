"""
Stream Watcher — handles RTSP video/audio and HTTP streams.

This module is a backward-compatible shim. The implementation has been moved
to the toonic.server.watchers.stream package.

Migration path:
    Old: from toonic.server.watchers.stream_watcher import StreamWatcher, Detection, FrameRecord
    New: from toonic.server.watchers.stream import StreamWatcher, Detection, FrameRecord
"""

from __future__ import annotations

# Re-export all public API from the new stream package
from toonic.server.watchers.stream.models import Detection, FrameRecord
from toonic.server.watchers.stream.watcher import StreamWatcher, _bool

__all__ = [
    "Detection",
    "FrameRecord",
    "StreamWatcher",
]
