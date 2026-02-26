"""
Video handlers — Video files and RTSP streams
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toonic.core.base import BaseHandlerMixin
from toonic.core.registry import FormatRegistry


# =============================================================================
# Modele logiki video
# =============================================================================

@dataclass
class KeyframeSpec:
    """Pojedynczy keyframe z video."""
    timestamp_s: float
    camera_id: int = 0
    scene_change_score: float = 0.0
    width: int = 160
    height: int = 120
    jpeg_quality: int = 10
    b64_data: str = ""
    size_bytes: int = 0


@dataclass
class VideoSegment:
    """Segment video — zgrupowane keyframes + audio."""
    index: int
    start_s: float
    end_s: float
    keyframes: List[KeyframeSpec] = field(default_factory=list)
    audio_b64: str = ""
    scene_changes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoLogic:
    """Logika video — implementuje FileLogic Protocol."""
    source_file: str
    source_hash: str
    file_category: str = "video"

    duration_s: float = 0.0
    fps: float = 0.0
    original_width: int = 0
    original_height: int = 0
    codec: str = ""
    num_cameras: int = 1
    segments: List[VideoSegment] = field(default_factory=list)
    total_keyframes: int = 0
    scene_threshold: float = 0.4
    lowq_resolution: Tuple[int, int] = (160, 120)
    lowq_quality: int = 10
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "duration_s": self.duration_s,
            "fps": self.fps,
            "resolution": f"{self.original_width}x{self.original_height}",
            "codec": self.codec,
            "num_cameras": self.num_cameras,
            "total_keyframes": self.total_keyframes,
            "segments": len(self.segments),
            "lowq": f"{self.lowq_resolution[0]}x{self.lowq_resolution[1]} Q={self.lowq_quality}",
        }

    def complexity(self) -> int:
        return self.total_keyframes * 2 + len(self.segments)


# =============================================================================
# Multi-cam RTSP capture buffer
# =============================================================================

class LowQRTSPExtractor:
    """Pure OpenCV RTSP → low-quality keyframe buffer."""

    def __init__(
        self,
        rtsp_urls: List[str],
        frame_size: Tuple[int, int] = (160, 120),
        quality: int = 10,
        buffer_size: int = 30,
    ):
        self.rtsp_urls = rtsp_urls
        self.frame_size = frame_size
        self.quality = quality
        self.buffers: List[deque] = [deque(maxlen=buffer_size) for _ in rtsp_urls]
        self.caps: List[Any] = []
        self.threads: List[threading.Thread] = []
        self.running = False

    def start(self) -> None:
        try:
            import cv2
        except ImportError:
            raise ImportError("pip install opencv-python")

        self.running = True
        for i, url in enumerate(self.rtsp_urls):
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            self.caps.append(cap)
            t = threading.Thread(
                target=self._capture_thread,
                args=(cap, self.buffers[i], i),
                daemon=True,
            )
            t.start()
            self.threads.append(t)

    def stop(self) -> None:
        self.running = False
        for cap in self.caps:
            cap.release()

    def _capture_thread(self, cap: Any, buffer: deque, idx: int) -> None:
        import cv2
        while self.running and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, self.frame_size)
                _, buf = cv2.imencode(
                    '.jpg', frame,
                    [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                )
                buffer.append({
                    'b64': base64.b64encode(buf).decode(),
                    'ts': time.time(),
                    'cam': idx,
                    'size': len(buf),
                })
            time.sleep(0.033)

    def get_sync_frame(self) -> List[Optional[Dict]]:
        return [buf[-1] if buf else None for buf in self.buffers]

    def get_all_recent(self, n: int = 5) -> List[List[Dict]]:
        return [list(buf)[-n:] for buf in self.buffers]


# =============================================================================
# Scene change detection (Pure OpenCV)
# =============================================================================

class SceneDetector:
    """Detekcja zmian scen — pixel diff bez AI."""

    def __init__(self, threshold: float = 0.4):
        self.threshold = threshold
        self.prev_frame = None

    def is_scene_change(self, frame_bytes: bytes) -> Tuple[bool, float]:
        import cv2
        import numpy as np

        frame = cv2.imdecode(
            np.frombuffer(frame_bytes, np.uint8),
            cv2.IMREAD_GRAYSCALE
        )

        if self.prev_frame is None:
            self.prev_frame = frame
            return True, 1.0

        diff = cv2.absdiff(self.prev_frame, frame)
        change_ratio = float(np.mean(diff)) / 255.0

        is_change = change_ratio > self.threshold
        if is_change:
            self.prev_frame = frame

        return is_change, round(change_ratio, 3)

    def detect_from_file(self, video_path: str, sample_every_s: float = 1.0) -> List[KeyframeSpec]:
        import cv2

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        sample_interval = int(fps * sample_every_s)

        keyframes: List[KeyframeSpec] = []
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                small = cv2.resize(frame, (160, 120))
                _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 10])

                is_change, score = self.is_scene_change(buf.tobytes())
                if is_change:
                    keyframes.append(KeyframeSpec(
                        timestamp_s=round(frame_idx / fps, 2),
                        scene_change_score=score,
                        b64_data=base64.b64encode(buf).decode(),
                        size_bytes=len(buf),
                    ))

            frame_idx += 1

        cap.release()
        return keyframes


# =============================================================================
# Video File Handler
# =============================================================================

class VideoFileHandler(BaseHandlerMixin):
    """Handler dla plików video (.mp4, .avi, .mkv, .mov, .webm)."""

    extensions = frozenset({'.mp4', '.avi', '.mkv', '.mov', '.webm'})
    category = 'video'
    requires = ('cv2',)

    def parse(self, path: Path) -> VideoLogic:
        import cv2

        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        cap.release()

        detector = SceneDetector(threshold=0.4)
        keyframes = detector.detect_from_file(str(path), sample_every_s=1.0)

        segments = []
        seg_duration = 10.0
        for seg_idx in range(int(duration / seg_duration) + 1):
            start = seg_idx * seg_duration
            end = min(start + seg_duration, duration)
            seg_kf = [kf for kf in keyframes if start <= kf.timestamp_s < end]
            if seg_kf:
                segments.append(VideoSegment(
                    index=seg_idx,
                    start_s=start,
                    end_s=end,
                    keyframes=seg_kf,
                    scene_changes=len(seg_kf),
                ))

        return VideoLogic(
            source_file=path.name,
            source_hash=self._compute_hash(path),
            duration_s=round(duration, 2),
            fps=round(fps, 1),
            original_width=width,
            original_height=height,
            total_keyframes=len(keyframes),
            segments=segments,
        )

    def to_spec(self, logic: VideoLogic, fmt: str = 'toon') -> str:
        if fmt == 'toon':
            return self._to_toon(logic)
        return json.dumps(logic.to_dict(), indent=2, ensure_ascii=False)

    def _to_toon(self, v: VideoLogic) -> str:
        lines = [
            f"# {v.source_file} | video | {v.duration_s}s | "
            f"{v.original_width}x{v.original_height} | "
            f"{v.total_keyframes} keyframes"
        ]

        total_size = sum(
            kf.size_bytes for seg in v.segments for kf in seg.keyframes
        )
        lines.append(f"# lowq: {v.lowq_resolution[0]}x{v.lowq_resolution[1]} "
                     f"Q={v.lowq_quality} | total:{total_size/1024:.1f}kB")

        lines.append(f"S[{len(v.segments)}]:")
        for seg in v.segments:
            scores = [f"{kf.scene_change_score:.2f}" for kf in seg.keyframes[:5]]
            lines.append(
                f"  S{seg.index}[{seg.start_s:.0f}-{seg.end_s:.0f}s]: "
                f"kf[{len(seg.keyframes)}] scene:{','.join(scores)}"
            )

        if v.total_keyframes <= 50:
            lines.append(f"KF[{v.total_keyframes}]:")
            for seg in v.segments:
                for kf in seg.keyframes:
                    lines.append(
                        f"  F{kf.timestamp_s:.1f}s: "
                        f"data:image/jpeg;base64,{kf.b64_data[:60]}..."
                    )

        return '\n'.join(lines)

    def reproduce(self, logic: VideoLogic, client: Any = None, target_fmt: str | None = None) -> str:
        lines = [f"# Video timeline: {logic.source_file}"]
        for seg in logic.segments:
            lines.append(f"[{seg.start_s:.0f}s-{seg.end_s:.0f}s] "
                        f"{seg.scene_changes} scene changes")
        return '\n'.join(lines)

    def sniff(self, path: Path, content: str) -> float:
        return 0.8 if path.suffix.lower() in self.extensions else 0.0


# =============================================================================
# Rejestracja
# =============================================================================

def register_video_handlers() -> None:
    """Rejestruje handlery video w FormatRegistry."""
    FormatRegistry.register(VideoFileHandler())
