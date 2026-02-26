"""
Stream Watcher — handles RTSP video/audio and HTTP streams.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.stream")


class StreamWatcher(BaseWatcher):
    """Watches RTSP/HTTP streams, extracts keyframes and audio segments."""

    category = SourceCategory.VIDEO

    def __init__(self, source_id: str, path_or_url: str, **options):
        super().__init__(source_id, path_or_url, **options)
        self.poll_interval = float(options.get("poll_interval", 5.0))
        self.scene_threshold = float(options.get("scene_threshold", 0.4))
        self.frame_width = int(options.get("frame_width", 160))
        self.frame_height = int(options.get("frame_height", 120))
        self.jpeg_quality = int(options.get("jpeg_quality", 10))
        self._task: asyncio.Task | None = None
        self._frame_count = 0
        self._keyframe_count = 0

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
            await self._capture_opencv()
        except ImportError:
            logger.warning(f"[{self.source_id}] OpenCV not available, using mock stream")
            await self._capture_mock()
        except Exception as e:
            logger.error(f"[{self.source_id}] Capture error: {e}")
            await self._capture_mock()

    async def _capture_opencv(self) -> None:
        """Capture from RTSP/file using OpenCV."""
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(self.path_or_url)
        if not cap.isOpened():
            logger.error(f"[{self.source_id}] Cannot open: {self.path_or_url}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        prev_gray = None
        sample_interval = max(1, int(fps * self.poll_interval))

        logger.info(f"[{self.source_id}] OpenCV capture started (fps={fps:.1f})")

        while self.running:
            ret, frame = cap.read()
            if not ret:
                if Path(self.path_or_url).exists():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop video files
                    continue
                await asyncio.sleep(1.0)
                continue

            self._frame_count += 1
            if self._frame_count % sample_interval != 0:
                await asyncio.sleep(0.001)
                continue

            # Resize + encode
            small = cv2.resize(frame, (self.frame_width, self.frame_height))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            # Scene change detection
            is_keyframe = False
            score = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                score = float(np.mean(diff)) / 255.0
                is_keyframe = score > self.scene_threshold
            else:
                is_keyframe = True
                score = 1.0

            if is_keyframe:
                prev_gray = gray
                self._keyframe_count += 1

                _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                b64 = base64.b64encode(buf.tobytes()).decode()

                toon = (
                    f"# {self.source_id} | video-frame | "
                    f"kf:{self._keyframe_count} | scene:{score:.2f} | "
                    f"{self.frame_width}x{self.frame_height} Q={self.jpeg_quality}"
                )

                await self.emit(ContextChunk(
                    source_id=self.source_id,
                    category=SourceCategory.VIDEO,
                    toon_spec=toon,
                    raw_data=buf.tobytes(),
                    raw_encoding="base64_jpeg",
                    is_delta=True,
                    metadata={
                        "frame": self._frame_count,
                        "keyframe": self._keyframe_count,
                        "scene_score": round(score, 3),
                        "b64_preview": b64[:100],
                        "size_bytes": len(buf),
                    },
                ))

            await asyncio.sleep(0.01)

        cap.release()

    async def _capture_mock(self) -> None:
        """Mock stream — generates synthetic keyframe events for testing."""
        logger.info(f"[{self.source_id}] Mock stream started")
        seg_index = 0

        while self.running:
            await asyncio.sleep(self.poll_interval)
            seg_index += 1
            self._keyframe_count += 1

            toon = (
                f"# {self.source_id} | video-mock | "
                f"seg:{seg_index} kf:{self._keyframe_count} | "
                f"scene:0.50 | {self.frame_width}x{self.frame_height}"
            )

            await self.emit(ContextChunk(
                source_id=self.source_id,
                category=SourceCategory.VIDEO,
                toon_spec=toon,
                is_delta=True,
                metadata={
                    "mock": True,
                    "segment": seg_index,
                    "keyframe": self._keyframe_count,
                },
            ))

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        p = path_or_url.lower()
        if p.startswith("rtsp://"):
            return 0.95
        if any(p.endswith(x) for x in (".mp4", ".avi", ".mkv", ".mov", ".webm")):
            return 0.8
        if p.startswith(("http://", "https://")) and "stream" in p:
            return 0.5
        return 0.0


WatcherRegistry.register(StreamWatcher)
