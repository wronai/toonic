"""Stream Watcher — handles RTSP video/audio and HTTP streams.

Supports two modes:
  1. **Basic mode** (OpenCV only): scene-change detection via pixel diff,
     emits keyframes + periodic heartbeats.
  2. **Detection mode** (OpenCV + Ultralytics YOLO): pre-detects objects
     (person, car, etc.), buffers multi-frame event sequences, extracts
     ROI crops around detections, and only sends confirmed events to LLM.

Detection mode activates automatically when ``ultralytics`` is installed
and ``detect_objects=True`` (default). Falls back to basic mode otherwise.

This module is the main entry point - the implementation is split across:
- models.py: Detection, FrameRecord dataclasses
- capture.py: OpenCV and mock capture implementations  
- detection.py: YOLO initialization and inference
- events.py: Event confirmation and emission logic
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from toonic.server.models import SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

# Import implementations from submodules
from toonic.server.watchers.stream.models import Detection, FrameRecord
from toonic.server.watchers.stream.capture import capture_opencv, capture_mock

logger = logging.getLogger("toonic.watcher.stream")


def _bool(v) -> bool:
    """Parse bool from various representations."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


class StreamWatcher(BaseWatcher):
    """Watches RTSP/HTTP streams with optional YOLO pre-detection.

    Key options (pass via ``**options`` or YAML source config):
      - ``detect_objects``  : bool  — enable YOLO detection (default True)
      - ``detect_model``    : str   — YOLO model path (default "yolov8n.pt")
      - ``detect_conf``     : float — detection confidence threshold (default 0.4)
      - ``detect_classes``  : str   — comma-sep class names to keep (default "person,car,truck,bicycle,motorcycle,bus,dog,cat")
      - ``detect_resolution``: int  — frame width for detection (default 640)
      - ``min_event_frames``: int   — min frames with detections to confirm event (default 2)
      - ``min_event_duration_s``: float — min seconds event must span (default 1.0)
      - ``roi_padding``     : float — bbox padding ratio for ROI crop (default 0.15)
      - ``roi_max_crops``   : int   — max ROI crops per emission (default 4)
      - ``send_resolution`` : int   — frame width for LLM sending (default 320)
      - ``send_quality``    : int   — JPEG quality for LLM images (default 40)
      - ``event_buffer_s``  : float — sliding window buffer duration (default 10.0)
      - ``poll_interval``   : float — seconds between sampled frames (default 2.0)
      - ``scene_threshold`` : float — scene change threshold (default 0.01)
      - ``max_silent_s``    : float — max seconds without any emission (default 60.0)
    """

    category = SourceCategory.VIDEO

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        # Sampling
        self.poll_interval = float(options.get("poll_interval", 2.0))
        self.scene_threshold = float(options.get("scene_threshold", 0.01))
        self.max_silent_s = float(options.get("max_silent_s", 60.0))
        # Detection
        self.detect_objects = _bool(options.get("detect_objects", True))
        self.detect_model = str(options.get("detect_model", "yolov8n.pt"))
        self.detect_conf = float(options.get("detect_conf", 0.4))
        self.detect_classes_str = str(options.get(
            "detect_classes", "person,car,truck,bicycle,motorcycle,bus,dog,cat"))
        self.detect_resolution = int(options.get("detect_resolution", 640))
        # Event confirmation
        self.min_event_frames = int(options.get("min_event_frames", 2))
        self.min_event_duration_s = float(options.get("min_event_duration_s", 1.0))
        self.event_buffer_s = float(options.get("event_buffer_s", 10.0))
        # ROI
        self.roi_padding = float(options.get("roi_padding", 0.15))
        self.roi_max_crops = int(options.get("roi_max_crops", 4))
        # LLM send resolution (separate from detection resolution)
        self.send_width = int(options.get("send_resolution", 320))
        self.send_quality = int(options.get("send_quality", 40))
        # Legacy compat (frame_width/height used by basic mode)
        self.frame_width = int(options.get("frame_width", 320))
        self.frame_height = int(options.get("frame_height", 240))
        self.jpeg_quality = int(options.get("jpeg_quality", 40))
        # Internal state
        self._task: asyncio.Task | None = None
        self._frame_count = 0
        self._keyframe_count = 0
        self._event_count = 0
        self._last_emit_time: float = 0.0
        self._yolo_model = None
        self._yolo_available = False
        self._detect_class_set: set = set()
        self._frame_buffer: deque = deque()

    async def start(self) -> None:
        await super().start()
        self._task = asyncio.create_task(self._capture_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _capture_loop(self) -> None:
        """Main capture loop — try OpenCV first, fallback to mock."""
        try:
            await capture_opencv(self)
        except ImportError:
            logger.warning(f"[{self.source_id}] OpenCV not available, using mock stream")
            await capture_mock(self)
        except Exception as e:
            logger.error(f"[{self.source_id}] Capture error: {e}")
            await capture_mock(self)

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith(("rtsp://", "rtsps://", "rtmp://")):
            return 0.95
        if any(p.endswith(x) for x in (".mp4", ".avi", ".mkv", ".mov", ".webm")):
            return 0.8
        if p.startswith(("http://", "https://")) and "stream" in p:
            return 0.5
        return 0.0


WatcherRegistry.register(StreamWatcher)
