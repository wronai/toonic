"""
Trigger DSL — YAML-based declarative trigger configuration.

Example YAML:
```yaml
triggers:
  - name: person-detected
    source: video
    mode: on_event          # periodic | on_event | hybrid
    events:
      - type: motion
        threshold: 0.15
        min_duration_s: 1.0
      - type: scene_change
        threshold: 0.4
    fallback:
      periodic_s: 60        # send frame anyway every 60s if no event
    actions:
      - send_to_llm
    goal: "describe what you see, focus on people and their activity"

  - name: error-spike
    source: logs
    mode: on_event
    events:
      - type: pattern
        regex: "ERROR|CRITICAL"
        count_threshold: 5
        window_s: 60
    actions:
      - send_to_llm
      - alert
    goal: "analyze the error spike and suggest root cause"

  - name: periodic-summary
    source: code
    mode: periodic
    interval_s: 300
    actions:
      - send_to_llm
    goal: "summarize recent code changes"
```
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("toonic.triggers.dsl")


# ═══════════════════════════════════════════════════════════════
# Event condition definitions
# ═══════════════════════════════════════════════════════════════

@dataclass
class EventCondition:
    """Single event detection condition."""
    type: str = "scene_change"      # motion|scene_change|object|audio_level|speech|pattern|anomaly|custom
    threshold: float = 0.3          # detection threshold (meaning depends on type)
    min_duration_s: float = 0.0     # object must be present for N seconds
    max_duration_s: float = 0.0     # max duration before forced trigger
    count_threshold: int = 1        # number of occurrences before trigger
    window_s: float = 0.0           # time window for count_threshold
    regex: str = ""                 # for pattern type
    label: str = ""                 # for object type: "person", "car", "fire"
    min_size_pct: float = 0.0       # min object size as % of frame (0-100)
    max_size_pct: float = 100.0     # max object size as % of frame
    min_speed: float = 0.0          # min movement speed (pixels/sec normalized)
    direction: str = ""             # movement direction filter: "left"|"right"|"up"|"down"|""
    negate: bool = False            # invert condition (trigger when NOT detected)
    params: Dict[str, Any] = field(default_factory=dict)  # extra detector params

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.type, "threshold": self.threshold}
        if self.min_duration_s > 0: d["min_duration_s"] = self.min_duration_s
        if self.max_duration_s > 0: d["max_duration_s"] = self.max_duration_s
        if self.count_threshold > 1: d["count_threshold"] = self.count_threshold
        if self.window_s > 0: d["window_s"] = self.window_s
        if self.regex: d["regex"] = self.regex
        if self.label: d["label"] = self.label
        if self.min_size_pct > 0: d["min_size_pct"] = self.min_size_pct
        if self.max_size_pct < 100: d["max_size_pct"] = self.max_size_pct
        if self.min_speed > 0: d["min_speed"] = self.min_speed
        if self.direction: d["direction"] = self.direction
        if self.negate: d["negate"] = self.negate
        if self.params: d["params"] = self.params
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> EventCondition:
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k) and k != "params"},
                   params=d.get("params", {}))


@dataclass
class FallbackConfig:
    """Fallback behavior when no events fire."""
    periodic_s: float = 0.0         # send data anyway every N seconds
    on_silence_s: float = 0.0       # trigger after N seconds of no events
    send_summary: bool = False      # send accumulated summary instead of raw

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        if self.periodic_s > 0: d["periodic_s"] = self.periodic_s
        if self.on_silence_s > 0: d["on_silence_s"] = self.on_silence_s
        if self.send_summary: d["send_summary"] = True
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> FallbackConfig:
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k)})


# ═══════════════════════════════════════════════════════════════
# Trigger rule
# ═══════════════════════════════════════════════════════════════

@dataclass
class TriggerRule:
    """Single trigger rule — when and how to send data to LLM."""
    name: str = "default"
    source: str = ""                 # source filter: "video"|"logs"|"code"|"audio"|"" (all)
    mode: str = "hybrid"             # periodic|on_event|hybrid
    events: List[EventCondition] = field(default_factory=list)
    event_logic: str = "any"         # any|all — how to combine events
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    interval_s: float = 30.0         # for periodic/hybrid mode
    cooldown_s: float = 5.0          # min time between triggers
    goal: str = ""                   # override goal for this trigger
    actions: List[str] = field(default_factory=lambda: ["send_to_llm"])
    enabled: bool = True
    priority: int = 5                # 1-10, higher = more important

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "mode": self.mode,
            "interval_s": self.interval_s,
        }
        if self.source: d["source"] = self.source
        if self.events: d["events"] = [e.to_dict() for e in self.events]
        if self.event_logic != "any": d["event_logic"] = self.event_logic
        fb = self.fallback.to_dict()
        if fb: d["fallback"] = fb
        if self.cooldown_s != 5.0: d["cooldown_s"] = self.cooldown_s
        if self.goal: d["goal"] = self.goal
        if self.actions != ["send_to_llm"]: d["actions"] = self.actions
        if not self.enabled: d["enabled"] = False
        if self.priority != 5: d["priority"] = self.priority
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TriggerRule:
        events = [EventCondition.from_dict(e) if isinstance(e, dict) else e
                  for e in d.get("events", [])]
        fallback = FallbackConfig.from_dict(d["fallback"]) if "fallback" in d and isinstance(d["fallback"], dict) else FallbackConfig()
        return cls(
            name=d.get("name", "default"),
            source=d.get("source", ""),
            mode=d.get("mode", "hybrid"),
            events=events,
            event_logic=d.get("event_logic", "any"),
            fallback=fallback,
            interval_s=d.get("interval_s", 30.0),
            cooldown_s=d.get("cooldown_s", 5.0),
            goal=d.get("goal", ""),
            actions=d.get("actions", ["send_to_llm"]),
            enabled=d.get("enabled", True),
            priority=d.get("priority", 5),
        )


# ═══════════════════════════════════════════════════════════════
# Top-level config
# ═══════════════════════════════════════════════════════════════

@dataclass
class TriggerConfig:
    """Top-level trigger configuration (multiple rules)."""
    triggers: List[TriggerRule] = field(default_factory=list)
    defaults: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.defaults:
            d["defaults"] = self.defaults
        d["triggers"] = [t.to_dict() for t in self.triggers]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TriggerConfig:
        triggers = [TriggerRule.from_dict(t) if isinstance(t, dict) else t
                    for t in d.get("triggers", [])]
        return cls(triggers=triggers, defaults=d.get("defaults", {}))

    def get_rules_for_source(self, source_category: str) -> List[TriggerRule]:
        """Get active rules that apply to a source category."""
        return [r for r in self.triggers
                if r.enabled and (not r.source or r.source == source_category)]


def load_triggers(yaml_str: str) -> TriggerConfig:
    """Parse YAML string into TriggerConfig."""
    try:
        import yaml
    except ModuleNotFoundError as e:
        raise ImportError(
            "PyYAML is required for triggers. Install with: pip install 'toonic[server]' or pip install pyyaml"
        ) from e
    data = yaml.safe_load(yaml_str)
    if not data:
        return TriggerConfig()
    return TriggerConfig.from_dict(data)


def dump_triggers(config: TriggerConfig) -> str:
    """Serialize TriggerConfig to YAML string."""
    try:
        import yaml
    except ModuleNotFoundError as e:
        raise ImportError(
            "PyYAML is required for triggers. Install with: pip install 'toonic[server]' or pip install pyyaml"
        ) from e
    return yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True)
