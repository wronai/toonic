"""Stream Watcher data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Tuple


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
