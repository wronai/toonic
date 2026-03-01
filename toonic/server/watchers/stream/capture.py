"""Stream capture implementations - OpenCV and mock."""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import FrameRecord
    from .watcher import StreamWatcher

logger = logging.getLogger("toonic.watcher.stream")


async def capture_opencv(watcher: "StreamWatcher") -> None:
    """Capture from RTSP/file using OpenCV with optional YOLO detection."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(watcher.path_or_url)
    if not cap.isOpened():
        logger.error(f"[{watcher.source_id}] Cannot open: {watcher.path_or_url}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    sample_interval = max(1, int(fps * watcher.poll_interval))
    prev_gray = None

    # Try initialising YOLO (non-blocking, best-effort)
    from .detection import init_yolo
    use_yolo = init_yolo(watcher)
    mode_label = "detection" if use_yolo else "basic"
    logger.info(
        f"[{watcher.source_id}] OpenCV capture started "
        f"(fps={fps:.1f}, sample_every={sample_interval}f, mode={mode_label})"
    )

    while watcher.running:
        ret, frame = cap.read()
        if not ret:
            if Path(watcher.path_or_url).exists():
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            await asyncio.sleep(1.0)
            continue

        watcher._frame_count += 1
        if watcher._frame_count % sample_interval != 0:
            await asyncio.sleep(0.001)
            continue

        now = time.time()

        # Resize for LLM sending
        h_orig, w_orig = frame.shape[:2]
        send_h = int(watcher.send_width * h_orig / w_orig)
        small = cv2.resize(frame, (watcher.send_width, send_h))
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

        is_keyframe = scene_score > watcher.scene_threshold
        prev_gray = gray

        # --- Detection mode ---
        if use_yolo:
            from .detection import run_detection
            detections = await run_detection(watcher, frame)
            from .models import FrameRecord
            record = FrameRecord(
                timestamp=now, frame_idx=watcher._frame_count,
                frame=frame, small=small, gray=gray,
                scene_score=scene_score, detections=detections,
                motion_mask=motion_mask,
            )
            watcher._frame_buffer.append(record)
            # Prune old frames from buffer
            cutoff = now - watcher.event_buffer_s
            while watcher._frame_buffer and watcher._frame_buffer[0].timestamp < cutoff:
                watcher._frame_buffer.popleft()

            # Check if we have a confirmed event
            from .events import check_event_and_emit, emit_heartbeat
            await check_event_and_emit(watcher, cv2, np)

            # Heartbeat fallback: emit even if no detections
            silent_elapsed = now - watcher._last_emit_time if watcher._last_emit_time else 0
            if watcher._last_emit_time > 0 and silent_elapsed >= watcher.max_silent_s:
                await emit_heartbeat(watcher, cv2, small, scene_score)

            if watcher._last_emit_time == 0:
                watcher._last_emit_time = now

        # --- Basic mode (no YOLO) ---
        else:
            await _handle_basic_mode(watcher, cv2, small, gray, now, is_keyframe, scene_score, send_h)

        await asyncio.sleep(0.01)

    cap.release()


async def _handle_basic_mode(
    watcher: "StreamWatcher",
    cv2,
    small,
    gray,
    now: float,
    is_keyframe: bool,
    scene_score: float,
    send_h: int
) -> None:
    """Handle basic mode without YOLO detection."""
    import base64
    from toonic.server.models import ContextChunk, ContentType, SourceCategory

    silent_elapsed = now - watcher._last_emit_time if watcher._last_emit_time else 0
    is_heartbeat = (
        not is_keyframe and watcher._last_emit_time > 0
        and silent_elapsed >= watcher.max_silent_s
    )
    if is_keyframe or is_heartbeat:
        watcher._keyframe_count += 1
        watcher._last_emit_time = now
        _, buf = cv2.imencode(
            ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, watcher.send_quality])
        b64 = base64.b64encode(buf.tobytes()).decode()
        reason = "keyframe" if is_keyframe else "heartbeat"
        toon = (
            f"# {watcher.source_id} | video-frame | "
            f"kf:{watcher._keyframe_count} | scene:{scene_score:.3f} | "
            f"{reason} | {watcher.send_width}x{send_h} Q={watcher.send_quality}"
        )
        ct = ContentType.VIDEO_EVENT if is_keyframe else ContentType.VIDEO_HEARTBEAT
        pri = 0.7 if is_keyframe else 0.2
        await watcher.emit(ContextChunk(
            source_id=watcher.source_id,
            category=SourceCategory.VIDEO,
            toon_spec=toon,
            raw_data=buf.tobytes(),
            raw_encoding="base64_jpeg",
            is_delta=True,
            content_type=ct,
            priority=pri,
            metadata={
                "frame": watcher._frame_count,
                "keyframe": watcher._keyframe_count,
                "scene_score": round(scene_score, 3),
                "reason": reason,
                "b64_preview": b64[:100],
                "size_bytes": len(buf),
            },
        ))
    elif watcher._last_emit_time == 0:
        watcher._last_emit_time = now


async def capture_mock(watcher: "StreamWatcher") -> None:
    """Mock stream - generates synthetic keyframe events for testing."""
    from toonic.server.models import ContextChunk, SourceCategory

    logger.info(f"[{watcher.source_id}] Mock stream started")
    seg_index = 0

    while watcher.running:
        await asyncio.sleep(watcher.poll_interval)
        seg_index += 1
        watcher._keyframe_count += 1

        toon = (
            f"# {watcher.source_id} | video-mock | "
            f"seg:{seg_index} kf:{watcher._keyframe_count} | "
            f"scene:0.50 | {watcher.frame_width}x{watcher.frame_height}"
        )

        await watcher.emit(ContextChunk(
            source_id=watcher.source_id,
            category=SourceCategory.VIDEO,
            toon_spec=toon,
            is_delta=True,
            metadata={
                "mock": True,
                "segment": seg_index,
                "keyframe": watcher._keyframe_count,
            },
        ))
