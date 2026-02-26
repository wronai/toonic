"""
Trigger Scheduler — evaluates trigger rules against incoming data,
decides when to dispatch context to LLM.

Supports three modes:
- periodic: send every N seconds regardless
- on_event: send only when event conditions are met
- hybrid: send on event OR after fallback period (whichever comes first)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from toonic.server.triggers.dsl import TriggerConfig, TriggerRule
from toonic.server.triggers.detectors import (
    BaseDetector, DetectionResult, create_detectors,
)

logger = logging.getLogger("toonic.triggers.scheduler")


@dataclass
class TriggerEvent:
    """Fired when a trigger rule decides to dispatch."""
    rule_name: str
    reason: str              # "periodic"|"event"|"fallback"|"hybrid"
    detections: List[DetectionResult] = field(default_factory=list)
    goal: str = ""
    source: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule_name,
            "reason": self.reason,
            "detections": [d.to_dict() for d in self.detections if d.triggered],
            "goal": self.goal,
            "timestamp": self.timestamp,
        }


class RuleState:
    """Runtime state for a single trigger rule."""

    def __init__(self, rule: TriggerRule):
        self.rule = rule
        self.detectors: List[BaseDetector] = create_detectors(rule.events)
        self.last_triggered: float = 0.0
        self.last_periodic: float = 0.0
        self.last_fallback: float = 0.0
        self.event_count: int = 0
        self.periodic_count: int = 0

    def evaluate(self, data: Dict[str, Any], source_category: str) -> Optional[TriggerEvent]:
        """Evaluate rule against data. Returns TriggerEvent if should fire."""
        now = time.time()

        # Check source filter
        if self.rule.source and self.rule.source != source_category:
            return None

        # Cooldown check
        if now - self.last_triggered < self.rule.cooldown_s:
            return None

        # Evaluate event conditions
        results = [d.evaluate(data) for d in self.detectors]
        any_triggered = any(r.triggered for r in results)
        all_triggered = all(r.triggered for r in results) if results else False

        event_match = False
        if self.rule.event_logic == "all":
            event_match = all_triggered
        else:
            event_match = any_triggered

        # ── Mode: periodic ───────────────────────────
        if self.rule.mode == "periodic":
            elapsed = now - self.last_periodic
            if elapsed >= self.rule.interval_s:
                self.last_periodic = now
                self.last_triggered = now
                self.periodic_count += 1
                return TriggerEvent(
                    rule_name=self.rule.name,
                    reason="periodic",
                    goal=self.rule.goal,
                    source=source_category,
                )
            return None

        # ── Mode: on_event ───────────────────────────
        if self.rule.mode == "on_event":
            if event_match:
                self.last_triggered = now
                self.event_count += 1
                return TriggerEvent(
                    rule_name=self.rule.name,
                    reason="event",
                    detections=[r for r in results if r.triggered],
                    goal=self.rule.goal,
                    source=source_category,
                )
            # Fallback periodic
            if self.rule.fallback.periodic_s > 0:
                elapsed = now - max(self.last_triggered, self.last_fallback)
                if elapsed >= self.rule.fallback.periodic_s:
                    self.last_fallback = now
                    self.last_triggered = now
                    return TriggerEvent(
                        rule_name=self.rule.name,
                        reason="fallback",
                        goal=self.rule.goal,
                        source=source_category,
                    )
            return None

        # ── Mode: hybrid (default) ───────────────────
        # Fire on event OR periodic, whichever comes first
        if event_match:
            self.last_triggered = now
            self.last_periodic = now  # reset periodic timer
            self.event_count += 1
            return TriggerEvent(
                rule_name=self.rule.name,
                reason="event",
                detections=[r for r in results if r.triggered],
                goal=self.rule.goal,
                source=source_category,
            )

        # Periodic fallback in hybrid mode
        elapsed_periodic = now - self.last_periodic
        if elapsed_periodic >= self.rule.interval_s:
            self.last_periodic = now
            self.last_triggered = now
            self.periodic_count += 1
            return TriggerEvent(
                rule_name=self.rule.name,
                reason="periodic",
                goal=self.rule.goal,
                source=source_category,
            )

        return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "rule": self.rule.name,
            "mode": self.rule.mode,
            "event_count": self.event_count,
            "periodic_count": self.periodic_count,
            "detectors": len(self.detectors),
            "last_triggered": self.last_triggered,
        }


class TriggerScheduler:
    """Manages all trigger rules and evaluates incoming data against them."""

    def __init__(self, config: TriggerConfig):
        self.config = config
        self._states: List[RuleState] = [RuleState(r) for r in config.triggers if r.enabled]
        self._callback: Optional[Callable] = None

    def on_trigger(self, callback: Callable[[TriggerEvent], Coroutine]) -> None:
        """Register callback for trigger events."""
        self._callback = callback

    def evaluate(self, data: Dict[str, Any], source_category: str = "") -> List[TriggerEvent]:
        """Evaluate all rules against data. Returns list of fired triggers."""
        events = []
        for state in self._states:
            event = state.evaluate(data, source_category)
            if event:
                events.append(event)
                logger.info(f"Trigger fired: {event.rule_name} ({event.reason})")
        return events

    async def evaluate_async(self, data: Dict[str, Any], source_category: str = "") -> List[TriggerEvent]:
        """Evaluate and call registered callback for each trigger."""
        events = self.evaluate(data, source_category)
        if self._callback:
            for event in events:
                try:
                    await self._callback(event)
                except Exception as e:
                    logger.error(f"Trigger callback error: {e}")
        return events

    def add_rule(self, rule: TriggerRule) -> None:
        """Add a rule at runtime."""
        self.config.triggers.append(rule)
        if rule.enabled:
            self._states.append(RuleState(rule))

    def remove_rule(self, name: str) -> None:
        """Remove a rule by name."""
        self.config.triggers = [r for r in self.config.triggers if r.name != name]
        self._states = [s for s in self._states if s.rule.name != name]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_rules": len(self._states),
            "rules": [s.get_stats() for s in self._states],
        }

    @classmethod
    def from_yaml(cls, yaml_str: str) -> TriggerScheduler:
        """Create scheduler from YAML string."""
        from toonic.server.triggers.dsl import load_triggers
        config = load_triggers(yaml_str)
        return cls(config)

    @classmethod
    def default_periodic(cls, interval_s: float = 30.0, goal: str = "") -> TriggerScheduler:
        """Create a simple periodic-only scheduler."""
        config = TriggerConfig(triggers=[
            TriggerRule(name="periodic", mode="periodic", interval_s=interval_s, goal=goal),
        ])
        return cls(config)
