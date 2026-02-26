"""
Event Detectors — detect events in video, audio, and text streams.

Each detector evaluates an EventCondition against incoming data and returns
a DetectionResult indicating whether the condition was met.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from toonic.server.triggers.dsl import EventCondition

logger = logging.getLogger("toonic.triggers.detectors")


@dataclass
class DetectionResult:
    """Result of a single detection evaluation."""
    triggered: bool = False
    event_type: str = ""
    score: float = 0.0
    label: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        d = {"triggered": self.triggered, "event_type": self.event_type, "score": self.score}
        if self.label: d["label"] = self.label
        if self.details: d["details"] = self.details
        return d


class BaseDetector:
    """Base class for event detectors."""

    def __init__(self, condition: EventCondition):
        self.condition = condition
        self._first_seen: float = 0.0
        self._event_times: deque = deque(maxlen=1000)

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        """Evaluate condition against incoming data. Override in subclasses."""
        return DetectionResult(triggered=False, event_type=self.condition.type)

    def _check_duration(self, currently_detected: bool) -> bool:
        """Check min_duration constraint."""
        now = time.time()
        if currently_detected:
            if self._first_seen == 0:
                self._first_seen = now
            elapsed = now - self._first_seen
            return elapsed >= self.condition.min_duration_s
        else:
            self._first_seen = 0.0
            return False

    def _check_count_window(self) -> bool:
        """Check count_threshold within window_s."""
        if self.condition.count_threshold <= 1:
            return True
        now = time.time()
        self._event_times.append(now)
        if self.condition.window_s > 0:
            cutoff = now - self.condition.window_s
            recent = [t for t in self._event_times if t >= cutoff]
        else:
            recent = list(self._event_times)
        return len(recent) >= self.condition.count_threshold


# ═══════════════════════════════════════════════════════════════
# Video detectors
# ═══════════════════════════════════════════════════════════════

class MotionDetector(BaseDetector):
    """Detect motion based on frame difference score."""

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        score = data.get("scene_score", data.get("motion_score", 0.0))
        raw = score >= self.condition.threshold

        if self.condition.min_duration_s > 0:
            triggered = self._check_duration(raw)
        else:
            triggered = raw

        if self.condition.negate:
            triggered = not triggered

        return DetectionResult(
            triggered=triggered,
            event_type="motion",
            score=score,
            details={"threshold": self.condition.threshold},
        )


class SceneChangeDetector(BaseDetector):
    """Detect significant scene changes."""

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        score = data.get("scene_score", 0.0)
        triggered = score >= self.condition.threshold

        if self.condition.negate:
            triggered = not triggered

        return DetectionResult(
            triggered=triggered,
            event_type="scene_change",
            score=score,
            details={"threshold": self.condition.threshold},
        )


class ObjectDetector(BaseDetector):
    """Detect specific objects via frame analysis metadata.
    
    Uses LLM-based or local detection results passed in data.
    Falls back to motion + size heuristics when no object detection is available.
    """

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        # Check if object detection results are in data
        objects = data.get("detected_objects", [])
        label = self.condition.label.lower()

        for obj in objects:
            obj_label = obj.get("label", "").lower()
            obj_confidence = obj.get("confidence", 0.0)
            obj_size_pct = obj.get("size_pct", 50.0)
            obj_speed = obj.get("speed", 0.0)

            if label and label not in obj_label:
                continue
            if obj_confidence < self.condition.threshold:
                continue
            if obj_size_pct < self.condition.min_size_pct:
                continue
            if obj_size_pct > self.condition.max_size_pct:
                continue
            if self.condition.min_speed > 0 and obj_speed < self.condition.min_speed:
                continue

            raw = True
            if self.condition.min_duration_s > 0:
                triggered = self._check_duration(raw)
            else:
                triggered = raw

            if self.condition.negate:
                triggered = not triggered

            return DetectionResult(
                triggered=triggered,
                event_type="object",
                score=obj_confidence,
                label=obj_label,
                details={
                    "size_pct": obj_size_pct,
                    "speed": obj_speed,
                    "target_label": label,
                },
            )

        # No matching object found
        if self.condition.min_duration_s > 0:
            self._check_duration(False)

        triggered = self.condition.negate  # trigger if negated
        return DetectionResult(
            triggered=triggered,
            event_type="object",
            score=0.0,
            label=label,
            details={"detected": False},
        )


# ═══════════════════════════════════════════════════════════════
# Audio detectors
# ═══════════════════════════════════════════════════════════════

class AudioLevelDetector(BaseDetector):
    """Detect audio level exceeding threshold."""

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        level = data.get("audio_level", data.get("rms", 0.0))
        triggered = level >= self.condition.threshold
        if self.condition.negate:
            triggered = not triggered
        return DetectionResult(
            triggered=triggered, event_type="audio_level",
            score=level, details={"threshold": self.condition.threshold},
        )


class SpeechDetector(BaseDetector):
    """Detect speech activity."""

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        has_speech = data.get("has_speech", data.get("vad", False))
        score = 1.0 if has_speech else 0.0

        raw = has_speech
        if self.condition.min_duration_s > 0:
            triggered = self._check_duration(raw)
        else:
            triggered = raw

        if self.condition.negate:
            triggered = not triggered

        return DetectionResult(
            triggered=triggered, event_type="speech",
            score=score, details={"has_speech": has_speech},
        )


# ═══════════════════════════════════════════════════════════════
# Text / Log detectors
# ═══════════════════════════════════════════════════════════════

class PatternDetector(BaseDetector):
    """Detect text patterns (regex) in log/text data."""

    def __init__(self, condition: EventCondition):
        super().__init__(condition)
        self._pattern = re.compile(condition.regex, re.IGNORECASE) if condition.regex else None

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        text = data.get("text", data.get("content", data.get("toon_spec", "")))
        if not self._pattern or not text:
            return DetectionResult(triggered=self.condition.negate, event_type="pattern", score=0.0)

        matches = self._pattern.findall(text)
        count = len(matches)

        if count > 0:
            for _ in range(count):
                self._event_times.append(time.time())

        # Check if enough events accumulated in window
        triggered = False
        if count > 0 and self.condition.count_threshold > 1:
            now = time.time()
            if self.condition.window_s > 0:
                cutoff = now - self.condition.window_s
                recent = [t for t in self._event_times if t >= cutoff]
            else:
                recent = list(self._event_times)
            triggered = len(recent) >= self.condition.count_threshold
        elif count > 0 and self.condition.count_threshold <= 1:
            triggered = True
        if self.condition.negate:
            triggered = not triggered

        return DetectionResult(
            triggered=triggered, event_type="pattern",
            score=min(count / max(self.condition.count_threshold, 1), 1.0),
            label=self.condition.regex,
            details={"match_count": count, "sample": matches[:3] if matches else []},
        )


class AnomalyDetector(BaseDetector):
    """Detect anomalies — significant deviation from recent history."""

    def __init__(self, condition: EventCondition):
        super().__init__(condition)
        self._history: deque = deque(maxlen=100)

    def evaluate(self, data: Dict[str, Any]) -> DetectionResult:
        value = data.get("value", data.get("score", data.get("metric", 0.0)))
        self._history.append(value)

        if len(self._history) < 5:
            return DetectionResult(triggered=False, event_type="anomaly", score=0.0)

        mean = sum(self._history) / len(self._history)
        variance = sum((x - mean) ** 2 for x in self._history) / len(self._history)
        std = variance ** 0.5 if variance > 0 else 0.001

        z_score = abs(value - mean) / std if std > 0 else 0.0
        triggered = z_score >= self.condition.threshold

        if self.condition.negate:
            triggered = not triggered

        return DetectionResult(
            triggered=triggered, event_type="anomaly",
            score=z_score,
            details={"value": value, "mean": round(mean, 3), "std": round(std, 3), "z_score": round(z_score, 2)},
        )


# ═══════════════════════════════════════════════════════════════
# Detector factory
# ═══════════════════════════════════════════════════════════════

_DETECTOR_MAP = {
    "motion": MotionDetector,
    "scene_change": SceneChangeDetector,
    "object": ObjectDetector,
    "audio_level": AudioLevelDetector,
    "speech": SpeechDetector,
    "pattern": PatternDetector,
    "anomaly": AnomalyDetector,
}


def create_detector(condition: EventCondition) -> BaseDetector:
    """Create appropriate detector for an EventCondition."""
    cls = _DETECTOR_MAP.get(condition.type)
    if cls:
        return cls(condition)
    logger.warning(f"Unknown detector type: {condition.type}, using base")
    return BaseDetector(condition)


def create_detectors(conditions: List[EventCondition]) -> List[BaseDetector]:
    """Create detectors for a list of conditions."""
    return [create_detector(c) for c in conditions]
