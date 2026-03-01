"""Event detection and emission logic for stream watcher."""
from __future__ import annotations

import base64
import logging
import time
from typing import TYPE_CHECKING, List

from toonic.server.models import ContextChunk, ContentType, SourceCategory

from .models import FrameRecord

if TYPE_CHECKING:
    from .watcher import StreamWatcher

logger = logging.getLogger("toonic.watcher.stream")


async def check_event_and_emit(watcher: "StreamWatcher", cv2, np) -> None:
    """Check buffered frames for a confirmed event and emit multi-frame chunk."""
    frames_with_det = [f for f in watcher._frame_buffer if f.detections]
    if len(frames_with_det) < watcher.min_event_frames:
        return
    # Check duration span
    duration = frames_with_det[-1].timestamp - frames_with_det[0].timestamp
    if duration < watcher.min_event_duration_s:
        return
    # Cooldown: don't re-emit the same event too quickly
    now = time.time()
    if watcher._last_emit_time > 0 and (now - watcher._last_emit_time) < watcher.min_event_duration_s:
        return

    watcher._event_count += 1
    watcher._keyframe_count += 1
    watcher._last_emit_time = now

    # Select representative frames (first, middle, last of detection window)
    selected = _select_event_frames(watcher, frames_with_det)

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
            ".jpg", fr.small, [cv2.IMWRITE_JPEG_QUALITY, watcher.send_quality])
        frame_images.append(buf.tobytes())

    # Extract ROI crops around detections (from high-res frames)
    roi_crops = _extract_roi_crops(watcher, cv2, selected)

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
            ".jpg", diff_vis, [cv2.IMWRITE_JPEG_QUALITY, watcher.send_quality])
        diff_image = diff_buf.tobytes()

    # Build TOON spec with event summary
    det_labels = ", ".join(f"{k}×{v}" for k, v in det_summary.items())
    toon = (
        f"# {watcher.source_id} | video-event #{watcher._event_count} | "
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

    await watcher.emit(ContextChunk(
        source_id=watcher.source_id,
        category=SourceCategory.VIDEO,
        toon_spec=toon,
        raw_data=primary_raw,
        raw_encoding="base64_jpeg",
        is_delta=True,
        content_type=ContentType.VIDEO_EVENT,
        priority=0.9,
        metadata={
            "frame": selected[-1].frame_idx,
            "keyframe": watcher._keyframe_count,
            "event_id": watcher._event_count,
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
        f"[{watcher.source_id}] Event #{watcher._event_count}: "
        f"{det_labels} | {len(selected)} frames/{duration:.1f}s | "
        f"{len(roi_crops)} ROI crops | {len(all_images)} images total"
    )
    # Clear processed frames from buffer to avoid re-emitting
    watcher._frame_buffer.clear()


def _select_event_frames(watcher: "StreamWatcher", frames: List[FrameRecord]) -> List[FrameRecord]:
    """Select representative frames from detection window (first, mid, last)."""
    if len(frames) <= 3:
        return list(frames)
    n = len(frames)
    indices = [0, n // 2, n - 1]
    return [frames[i] for i in indices]


def _extract_roi_crops(watcher: "StreamWatcher", cv2, frames: List[FrameRecord]) -> List[bytes]:
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
            pad_x = int((x2 - x1) * watcher.roi_padding)
            pad_y = int((y2 - y1) * watcher.roi_padding)
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
                ".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, watcher.send_quality])
            crops.append(buf.tobytes())
            if len(crops) >= watcher.roi_max_crops:
                return crops
    return crops


async def emit_heartbeat(watcher: "StreamWatcher", cv2, small, scene_score: float) -> None:
    """Emit a heartbeat frame when no events detected for max_silent_s."""
    watcher._keyframe_count += 1
    watcher._last_emit_time = time.time()
    _, buf = cv2.imencode(
        ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, watcher.send_quality])
    h, w = small.shape[:2]
    toon = (
        f"# {watcher.source_id} | video-frame | "
        f"kf:{watcher._keyframe_count} | scene:{scene_score:.3f} | "
        f"heartbeat | {w}x{h} Q={watcher.send_quality}"
    )
    await watcher.emit(ContextChunk(
        source_id=watcher.source_id,
        category=SourceCategory.VIDEO,
        toon_spec=toon,
        raw_data=buf.tobytes(),
        raw_encoding="base64_jpeg",
        is_delta=True,
        content_type=ContentType.VIDEO_HEARTBEAT,
        priority=0.2,
        metadata={
            "frame": watcher._frame_count,
            "keyframe": watcher._keyframe_count,
            "scene_score": round(scene_score, 3),
            "reason": "heartbeat",
            "size_bytes": len(buf),
        },
    ))
