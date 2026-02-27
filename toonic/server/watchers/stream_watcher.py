"""
Stream Watcher — handles RTSP video/audio and HTTP streams.

Supports two modes:
  1. **Basic mode** (OpenCV only): scene-change detection via pixel diff,
     emits keyframes + periodic heartbeats.
  2. **Detection mode** (OpenCV + Ultralytics YOLO): pre-detects objects
     (person, car, etc.), buffers multi-frame event sequences, extracts
     ROI crops around detections, and only sends confirmed events to LLM.

Detection mode activates automatically when ``ultralytics`` is installed
and ``detect_objects=True`` (default). Falls back to basic mode otherwise.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toonic.server.models import ContextChunk, ContentType, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry

logger = logging.getLogger("toonic.watcher.stream")

# ---------------------------------------------------------------------------
# Detection result dataclass
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """Single object detection from YOLO or similar."""
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2 in original frame coords
    track_id: int = -1


@dataclass
class FrameRecord:
    """Buffered frame with optional detections."""
    timestamp: float
    frame_idx: int
    frame: Any                       # np.ndarray (BGR, full-res for ROI crop)
    small: Any                       # np.ndarray (resized for LLM send)
    gray: Any                        # np.ndarray (grayscale of small)
    scene_score: float = 0.0
    detections: List[Detection] = field(default_factory=list)
    motion_mask: Any = None          # np.ndarray binary mask of changed pixels


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
        self._frame_buffer: deque[FrameRecord] = deque()

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

    # ------------------------------------------------------------------
    # YOLO initialisation
    # ------------------------------------------------------------------

    def _init_yolo(self) -> bool:
        """Try to load YOLO model. Returns True if successful."""
        if not self.detect_objects:
            return False
        try:
            from ultralytics import YOLO
            self._yolo_model = YOLO(self.detect_model, verbose=False)
            # Build class filter set
            self._detect_class_set = {
                c.strip().lower() for c in self.detect_classes_str.split(",") if c.strip()
            }
            logger.info(
                f"[{self.source_id}] YOLO loaded: {self.detect_model} "
                f"(conf={self.detect_conf}, classes={self._detect_class_set})"
            )
            self._yolo_available = True
            return True
        except ImportError:
            logger.info(f"[{self.source_id}] ultralytics not installed — basic mode")
            return False
        except Exception as e:
            logger.warning(f"[{self.source_id}] YOLO init failed: {e} — basic mode")
            return False

    # ------------------------------------------------------------------
    # Capture loop
    # ------------------------------------------------------------------

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
        """Capture from RTSP/file using OpenCV with optional YOLO detection."""
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(self.path_or_url)
        if not cap.isOpened():
            logger.error(f"[{self.source_id}] Cannot open: {self.path_or_url}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        sample_interval = max(1, int(fps * self.poll_interval))
        prev_gray = None

        # Try initialising YOLO (non-blocking, best-effort)
        use_yolo = self._init_yolo()
        mode_label = "detection" if use_yolo else "basic"
        logger.info(
            f"[{self.source_id}] OpenCV capture started "
            f"(fps={fps:.1f}, sample_every={sample_interval}f, mode={mode_label})"
        )

        while self.running:
            ret, frame = cap.read()
            if not ret:
                if Path(self.path_or_url).exists():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                await asyncio.sleep(1.0)
                continue

            self._frame_count += 1
            if self._frame_count % sample_interval != 0:
                await asyncio.sleep(0.001)
                continue

            now = time.time()

            # Resize for LLM sending
            h_orig, w_orig = frame.shape[:2]
            send_h = int(self.send_width * h_orig / w_orig)
            small = cv2.resize(frame, (self.send_width, send_h))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            # Scene change score
            scene_score = 0.0
            motion_mask = None
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                scene_score = float(np.mean(diff)) / 255.0
                # Binary motion mask (pixels that changed significantly)
                _, motion_mask = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
            else:
                scene_score = 1.0

            is_keyframe = scene_score > self.scene_threshold
            prev_gray = gray

            # --- Detection mode ---
            if use_yolo:
                detections = await self._run_detection(frame)
                record = FrameRecord(
                    timestamp=now, frame_idx=self._frame_count,
                    frame=frame, small=small, gray=gray,
                    scene_score=scene_score, detections=detections,
                    motion_mask=motion_mask,
                )
                self._frame_buffer.append(record)
                # Prune old frames from buffer
                cutoff = now - self.event_buffer_s
                while self._frame_buffer and self._frame_buffer[0].timestamp < cutoff:
                    self._frame_buffer.popleft()

                # Check if we have a confirmed event
                await self._check_event_and_emit(cv2, np)

                # Heartbeat fallback: emit even if no detections
                silent_elapsed = now - self._last_emit_time if self._last_emit_time else 0
                if self._last_emit_time > 0 and silent_elapsed >= self.max_silent_s:
                    await self._emit_heartbeat(cv2, small, scene_score)

                if self._last_emit_time == 0:
                    self._last_emit_time = now

            # --- Basic mode (no YOLO) ---
            else:
                silent_elapsed = now - self._last_emit_time if self._last_emit_time else 0
                is_heartbeat = (
                    not is_keyframe and self._last_emit_time > 0
                    and silent_elapsed >= self.max_silent_s
                )
                if is_keyframe or is_heartbeat:
                    self._keyframe_count += 1
                    self._last_emit_time = now
                    _, buf = cv2.imencode(
                        ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.send_quality])
                    b64 = base64.b64encode(buf.tobytes()).decode()
                    reason = "keyframe" if is_keyframe else "heartbeat"
                    toon = (
                        f"# {self.source_id} | video-frame | "
                        f"kf:{self._keyframe_count} | scene:{scene_score:.3f} | "
                        f"{reason} | {self.send_width}x{send_h} Q={self.send_quality}"
                    )
                    ct = ContentType.VIDEO_EVENT if is_keyframe else ContentType.VIDEO_HEARTBEAT
                    pri = 0.7 if is_keyframe else 0.2
                    await self.emit(ContextChunk(
                        source_id=self.source_id,
                        category=SourceCategory.VIDEO,
                        toon_spec=toon,
                        raw_data=buf.tobytes(),
                        raw_encoding="base64_jpeg",
                        is_delta=True,
                        content_type=ct,
                        priority=pri,
                        metadata={
                            "frame": self._frame_count,
                            "keyframe": self._keyframe_count,
                            "scene_score": round(scene_score, 3),
                            "reason": reason,
                            "b64_preview": b64[:100],
                            "size_bytes": len(buf),
                        },
                    ))
                elif self._last_emit_time == 0:
                    self._last_emit_time = now

            await asyncio.sleep(0.01)

        cap.release()

    # ------------------------------------------------------------------
    # YOLO detection (runs in thread to avoid blocking event loop)
    # ------------------------------------------------------------------

    async def _run_detection(self, frame) -> List[Detection]:
        """Run YOLO on a single frame. Returns filtered detections."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._detect_sync, frame)

    def _detect_sync(self, frame) -> List[Detection]:
        """Synchronous YOLO inference + filtering."""
        import cv2
        h, w = frame.shape[:2]
        # Resize for detection
        det_h = int(self.detect_resolution * h / w)
        det_frame = cv2.resize(frame, (self.detect_resolution, det_h))
        scale_x = w / self.detect_resolution
        scale_y = h / det_h

        try:
            results = self._yolo_model(det_frame, conf=self.detect_conf, verbose=False)
        except Exception as e:
            logger.debug(f"[{self.source_id}] YOLO inference error: {e}")
            return []

        detections = []
        for r in results:
            if r.boxes is None:
                continue
            names = r.names  # {0: 'person', 1: 'bicycle', ...}
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = names.get(cls_id, f"class_{cls_id}").lower()
                if self._detect_class_set and label not in self._detect_class_set:
                    continue
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                # Scale back to original frame coordinates
                detections.append(Detection(
                    label=label,
                    confidence=round(conf, 3),
                    bbox=(
                        int(x1 * scale_x), int(y1 * scale_y),
                        int(x2 * scale_x), int(y2 * scale_y),
                    ),
                    track_id=int(box.id[0]) if box.id is not None else -1,
                ))
        return detections

    # ------------------------------------------------------------------
    # Event confirmation + emission (detection mode)
    # ------------------------------------------------------------------

    async def _check_event_and_emit(self, cv2, np) -> None:
        """Check buffered frames for a confirmed event and emit multi-frame chunk."""
        frames_with_det = [f for f in self._frame_buffer if f.detections]
        if len(frames_with_det) < self.min_event_frames:
            return
        # Check duration span
        duration = frames_with_det[-1].timestamp - frames_with_det[0].timestamp
        if duration < self.min_event_duration_s:
            return
        # Cooldown: don't re-emit the same event too quickly
        now = time.time()
        if self._last_emit_time > 0 and (now - self._last_emit_time) < self.min_event_duration_s:
            return

        self._event_count += 1
        self._keyframe_count += 1
        self._last_emit_time = now

        # Select representative frames (first, middle, last of detection window)
        selected = self._select_event_frames(frames_with_det)

        # Gather all detections from selected frames
        all_dets = []
        for fr in selected:
            all_dets.extend(fr.detections)

        # Aggregate detected object labels + counts
        det_summary = {}
        for d in all_dets:
            det_summary[d.label] = det_summary.get(d.label, 0) + 1
        detected_objects = [
            {"label": k, "count": v, "confidence": max(
                d.confidence for d in all_dets if d.label == k
            )} for k, v in det_summary.items()
        ]

        # Encode selected frames as JPEG
        frame_images = []
        for fr in selected:
            _, buf = cv2.imencode(
                ".jpg", fr.small, [cv2.IMWRITE_JPEG_QUALITY, self.send_quality])
            frame_images.append(buf.tobytes())

        # Extract ROI crops around detections (from high-res frames)
        roi_crops = self._extract_roi_crops(cv2, selected)

        # Build motion diff image between first and last selected frames
        diff_image = None
        if len(selected) >= 2:
            diff_raw = cv2.absdiff(selected[0].gray, selected[-1].gray)
            _, diff_thresh = cv2.threshold(diff_raw, 15, 255, cv2.THRESH_BINARY)
            # Apply red overlay on the last frame to highlight changes
            diff_vis = selected[-1].small.copy()
            diff_color = cv2.cvtColor(diff_thresh, cv2.COLOR_GRAY2BGR)
            diff_color[:, :, 0] = 0  # zero blue
            diff_color[:, :, 1] = 0  # zero green → red only
            diff_vis = cv2.addWeighted(diff_vis, 0.7, diff_color, 0.3, 0)
            _, diff_buf = cv2.imencode(
                ".jpg", diff_vis, [cv2.IMWRITE_JPEG_QUALITY, self.send_quality])
            diff_image = diff_buf.tobytes()

        # Build TOON spec with event summary
        det_labels = ", ".join(f"{k}×{v}" for k, v in det_summary.items())
        toon = (
            f"# {self.source_id} | video-event #{self._event_count} | "
            f"detected: [{det_labels}] | "
            f"frames: {len(selected)} over {duration:.1f}s | "
            f"scene_Δ: {selected[-1].scene_score:.3f}"
        )

        # Pack all images: event frames + ROI crops + diff overlay
        all_images = frame_images + roi_crops
        if diff_image:
            all_images.append(diff_image)

        # Primary raw_data = first frame (for backward compat)
        primary_raw = frame_images[0] if frame_images else b""

        # Encode extra images as base64 list in metadata
        extra_images_b64 = [base64.b64encode(img).decode() for img in all_images[1:]]

        await self.emit(ContextChunk(
            source_id=self.source_id,
            category=SourceCategory.VIDEO,
            toon_spec=toon,
            raw_data=primary_raw,
            raw_encoding="base64_jpeg",
            is_delta=True,
            content_type=ContentType.VIDEO_EVENT,
            priority=0.9,
            metadata={
                "frame": selected[-1].frame_idx,
                "keyframe": self._keyframe_count,
                "event_id": self._event_count,
                "scene_score": round(selected[-1].scene_score, 3),
                "reason": "detection_event",
                "detected_objects": detected_objects,
                "detection_summary": det_summary,
                "event_duration_s": round(duration, 2),
                "event_frames": len(selected),
                "roi_crops_count": len(roi_crops),
                "has_diff_image": diff_image is not None,
                "extra_images_b64": extra_images_b64,
                "total_images": len(all_images),
                "size_bytes": sum(len(img) for img in all_images),
            },
        ))
        logger.info(
            f"[{self.source_id}] Event #{self._event_count}: "
            f"{det_labels} | {len(selected)} frames/{duration:.1f}s | "
            f"{len(roi_crops)} ROI crops | {len(all_images)} images total"
        )
        # Clear processed frames from buffer to avoid re-emitting
        self._frame_buffer.clear()

    def _select_event_frames(self, frames: List[FrameRecord]) -> List[FrameRecord]:
        """Select representative frames from detection window (first, mid, last)."""
        if len(frames) <= 3:
            return list(frames)
        n = len(frames)
        indices = [0, n // 2, n - 1]
        return [frames[i] for i in indices]

    def _extract_roi_crops(self, cv2, frames: List[FrameRecord]) -> List[bytes]:
        """Extract ROI crops around detected objects from high-res frames."""
        crops = []
        seen_labels = set()
        for fr in frames:
            for det in fr.detections:
                # Deduplicate: one crop per label (best confidence)
                if det.label in seen_labels:
                    continue
                seen_labels.add(det.label)
                x1, y1, x2, y2 = det.bbox
                h, w = fr.frame.shape[:2]
                # Add padding
                pad_x = int((x2 - x1) * self.roi_padding)
                pad_y = int((y2 - y1) * self.roi_padding)
                rx1 = max(0, x1 - pad_x)
                ry1 = max(0, y1 - pad_y)
                rx2 = min(w, x2 + pad_x)
                ry2 = min(h, y2 + pad_y)
                crop = fr.frame[ry1:ry2, rx1:rx2]
                if crop.size == 0:
                    continue
                # Resize crop to reasonable size for LLM
                crop_w = min(320, crop.shape[1])
                crop_h = int(crop_w * crop.shape[0] / crop.shape[1])
                crop = cv2.resize(crop, (crop_w, crop_h))
                _, buf = cv2.imencode(
                    ".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, self.send_quality])
                crops.append(buf.tobytes())
                if len(crops) >= self.roi_max_crops:
                    return crops
        return crops

    # ------------------------------------------------------------------
    # Heartbeat (detection mode fallback for quiet scenes)
    # ------------------------------------------------------------------

    async def _emit_heartbeat(self, cv2, small, scene_score: float) -> None:
        """Emit a heartbeat frame when no events detected for max_silent_s."""
        self._keyframe_count += 1
        self._last_emit_time = time.time()
        _, buf = cv2.imencode(
            ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.send_quality])
        h, w = small.shape[:2]
        toon = (
            f"# {self.source_id} | video-frame | "
            f"kf:{self._keyframe_count} | scene:{scene_score:.3f} | "
            f"heartbeat | {w}x{h} Q={self.send_quality}"
        )
        await self.emit(ContextChunk(
            source_id=self.source_id,
            category=SourceCategory.VIDEO,
            toon_spec=toon,
            raw_data=buf.tobytes(),
            raw_encoding="base64_jpeg",
            is_delta=True,
            content_type=ContentType.VIDEO_HEARTBEAT,
            priority=0.2,
            metadata={
                "frame": self._frame_count,
                "keyframe": self._keyframe_count,
                "scene_score": round(scene_score, 3),
                "reason": "heartbeat",
                "size_bytes": len(buf),
            },
        ))

    # ------------------------------------------------------------------
    # Mock stream (testing without real camera)
    # ------------------------------------------------------------------

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
        if p.startswith(("rtsp://", "rtsps://", "rtmp://")):
            return 0.95
        if any(p.endswith(x) for x in (".mp4", ".avi", ".mkv", ".mov", ".webm")):
            return 0.8
        if p.startswith(("http://", "https://")) and "stream" in p:
            return 0.5
        return 0.0


def _bool(v) -> bool:
    """Parse bool from various representations."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    return bool(v)


WatcherRegistry.register(StreamWatcher)
