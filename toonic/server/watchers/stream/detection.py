"""YOLO detection logic for stream watcher."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List

from .models import Detection

if TYPE_CHECKING:
    from .watcher import StreamWatcher

logger = logging.getLogger("toonic.watcher.stream")


def init_yolo(watcher: "StreamWatcher") -> bool:
    """Try to load YOLO model. Returns True if successful."""
    if not watcher.detect_objects:
        return False
    try:
        from ultralytics import YOLO
        watcher._yolo_model = YOLO(watcher.detect_model, verbose=False)
        # Build class filter set
        watcher._detect_class_set = {
            c.strip().lower() for c in watcher.detect_classes_str.split(",") if c.strip()
        }
        logger.info(
            f"[{watcher.source_id}] YOLO loaded: {watcher.detect_model} "
            f"(conf={watcher.detect_conf}, classes={watcher._detect_class_set})"
        )
        watcher._yolo_available = True
        return True
    except ImportError:
        logger.info(f"[{watcher.source_id}] ultralytics not installed - basic mode")
        return False
    except Exception as e:
        logger.warning(f"[{watcher.source_id}] YOLO init failed: {e} - basic mode")
        return False


async def run_detection(watcher: "StreamWatcher", frame) -> List[Detection]:
    """Run YOLO on a single frame. Returns filtered detections."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _detect_sync, watcher, frame)


def _detect_sync(watcher: "StreamWatcher", frame) -> List[Detection]:
    """Synchronous YOLO inference + filtering."""
    import cv2
    h, w = frame.shape[:2]
    # Resize for detection
    det_h = int(watcher.detect_resolution * h / w)
    det_frame = cv2.resize(frame, (watcher.detect_resolution, det_h))
    scale_x = w / watcher.detect_resolution
    scale_y = h / det_h

    try:
        results = watcher._yolo_model(det_frame, conf=watcher.detect_conf, verbose=False)
    except Exception as e:
        logger.debug(f"[{watcher.source_id}] YOLO inference error: {e}")
        return []

    detections = []
    for r in results:
        if r.boxes is None:
            continue
        names = r.names  # {0: 'person', 1: 'bicycle', ...}
        for box in r.boxes:
            cls_id = int(box.cls[0])
            label = names.get(cls_id, f"class_{cls_id}").lower()
            if watcher._detect_class_set and label not in watcher._detect_class_set:
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
