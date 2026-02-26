"""
NLP2YAML — converts natural language trigger descriptions to YAML DSL.

Uses LLM to parse human intent like:
  "send frame when person detected for 1 second, otherwise every 60 seconds"

Into structured TriggerConfig YAML.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from toonic.server.triggers.dsl import (
    TriggerConfig, TriggerRule, EventCondition, FallbackConfig,
    load_triggers, dump_triggers,
)

logger = logging.getLogger("toonic.triggers.nlp2yaml")

# ═══════════════════════════════════════════════════════════════
# Schema reference for the LLM
# ═══════════════════════════════════════════════════════════════

YAML_SCHEMA_PROMPT = '''You are a YAML trigger configuration generator for Toonic Server.
Convert the user's natural language description into a valid YAML trigger config.

YAML DSL schema:
```yaml
triggers:
  - name: <descriptive-name>
    source: video|audio|logs|code|config|""  # empty = all sources
    mode: periodic|on_event|hybrid
    interval_s: 30.0                          # for periodic/hybrid
    cooldown_s: 5.0                           # min seconds between triggers
    event_logic: any|all                      # how to combine events
    events:
      - type: motion|scene_change|object|audio_level|speech|pattern|anomaly
        threshold: 0.3              # detection sensitivity (0.0-1.0)
        min_duration_s: 0.0         # object must persist for N seconds
        count_threshold: 1          # N occurrences before trigger
        window_s: 0.0               # time window for count_threshold
        regex: ""                   # for pattern type
        label: ""                   # for object type: "person", "car"
        min_size_pct: 0.0           # min object size as % of frame
        max_size_pct: 100.0
        min_speed: 0.0              # movement speed
        negate: false               # invert (trigger when NOT detected)
    fallback:
      periodic_s: 60.0             # fallback: send every N seconds anyway
      on_silence_s: 0.0            # trigger after N seconds of quiet
    goal: "override goal for this trigger"
    actions: [send_to_llm]
    priority: 5                     # 1-10
```

Event types:
- motion: frame difference > threshold (video)
- scene_change: large visual change > threshold (video)
- object: specific object detected (person, car, fire) with label
- audio_level: sound volume > threshold (audio)
- speech: voice activity detected (audio)
- pattern: regex match in text/logs
- anomaly: statistical deviation from normal

Rules:
- Output ONLY valid YAML, no explanation
- Use "hybrid" mode when user wants both event-based AND periodic fallback
- Set fallback.periodic_s when user says "otherwise every N seconds" or "at minimum every N"
- For "person detected for 1 second": use object type with label="person" and min_duration_s=1.0
- For "every N seconds": use periodic mode with interval_s=N
- For "when X happens": use on_event mode
- For "when X happens or every N seconds": use hybrid mode or on_event with fallback
- Keep names descriptive and lowercase with hyphens
'''


class NLP2YAML:
    """Converts natural language to YAML trigger configuration via LLM."""

    def __init__(self, model: str = "", api_key: str = ""):
        self.model = model or os.environ.get("LLM_MODEL", "google/gemini-3-flash-preview")
        self.api_key = api_key or os.environ.get("LLM_API_KEY",
                       os.environ.get("OPENROUTER_API_KEY", ""))

    async def generate(self, description: str, source: str = "", goal: str = "") -> TriggerConfig:
        """Generate TriggerConfig from natural language description."""
        # Try local parsing first (for simple cases)
        config = self._try_local_parse(description, source, goal)
        if config and config.triggers:
            logger.info(f"NLP2YAML: local parse succeeded for: {description[:60]}")
            return config

        # Use LLM for complex descriptions
        yaml_str = await self._generate_via_llm(description, source, goal)
        if yaml_str:
            try:
                config = load_triggers(yaml_str)
                # Apply goal override
                if goal:
                    for t in config.triggers:
                        if not t.goal:
                            t.goal = goal
                logger.info(f"NLP2YAML: LLM generated {len(config.triggers)} trigger(s)")
                return config
            except Exception as e:
                logger.error(f"NLP2YAML: failed to parse LLM output: {e}")

        # Fallback: create simple periodic trigger
        logger.warning("NLP2YAML: falling back to default periodic trigger")
        return TriggerConfig(triggers=[
            TriggerRule(name="default", mode="periodic", interval_s=30.0, goal=goal, source=source),
        ])

    def generate_yaml(self, description: str, source: str = "", goal: str = "") -> str:
        """Synchronous YAML generation (local parse only, no LLM)."""
        config = self._try_local_parse(description, source, goal)
        if config and config.triggers:
            return dump_triggers(config)
        return ""

    # ── Local parser (handles common patterns without LLM) ────

    def _try_local_parse(self, desc: str, source: str = "", goal: str = "") -> Optional[TriggerConfig]:
        """Parse common natural language patterns locally."""
        d = desc.lower().strip()
        rules = []

        # Extract time values
        periodic_s = self._extract_time(d, r'(?:every|each|co)\s+(\d+(?:\.\d+)?)\s*(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:ours?)?)')
        fallback_s = self._extract_time(d, r'(?:otherwise|else|if\s+not|at\s+(?:least|minimum)|min\.?)\s+(?:every\s+)?(\d+(?:\.\d+)?)\s*(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?)')
        duration_s = self._extract_time(d, r'(?:for|during|lasting)\s+(\d+(?:\.\d+)?)\s*(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?)')

        events = []
        mode = "periodic"

        # Detect object conditions
        # First try: "object <noun>" pattern
        obj_match = re.search(r'\bobject\s+(\w+)', d)
        if obj_match:
            label = obj_match.group(1).rstrip("s")
            if label in ("people",): label = "person"
        else:
            # Standalone object nouns
            obj_match = re.search(r'\b(person|people|car|vehicle|animal|fire|smoke|face)\w*\b', d)
            if obj_match:
                label = obj_match.group(1).rstrip("s")
                if label in ("people",): label = "person"
                if label in ("vehicles",): label = "vehicle"
            else:
                label = None
        if obj_match and label:
            events.append(EventCondition(
                type="object", label=label, threshold=0.3,
                min_duration_s=duration_s if duration_s else 0.0,
            ))
            mode = "on_event"

        # Detect motion conditions
        if re.search(r'\bmotion\b|\bmovement\b|\bmoving\b', d):
            threshold = self._extract_float(d, r'motion\w*\s+(?:>|above|threshold)?\s*(\d+(?:\.\d+)?)', 0.15)
            events.append(EventCondition(type="motion", threshold=threshold,
                                         min_duration_s=duration_s or 0.0))
            mode = "on_event"

        # Detect scene change
        if re.search(r'scene\s*change|big\s*change|significant\s*change', d):
            threshold = self._extract_float(d, r'change\w*\s+(?:>|above|threshold)?\s*(\d+(?:\.\d+)?)', 0.4)
            events.append(EventCondition(type="scene_change", threshold=threshold))
            mode = "on_event"

        # Detect pattern/error conditions
        pattern_match = re.search(r'(?:pattern|error|warning|critical|exception|regex)\s*[:\s]*["\']?([^"\']+)["\']?', d)
        if pattern_match and any(w in d for w in ["error", "warning", "critical", "pattern", "regex", "exception"]):
            regex = pattern_match.group(1).strip()
            if regex in ("error", "warning", "critical", "exception"):
                regex = "ERROR|CRITICAL|EXCEPTION"
            count = int(self._extract_float(d, r'(\d+)\s+(?:times|occurrences|errors)', 1))
            window = self._extract_time(d, r'(?:in|within)\s+(\d+(?:\.\d+)?)\s*(s(?:ec)?|m(?:in)?|h)')
            events.append(EventCondition(type="pattern", regex=regex,
                                         count_threshold=max(count, 1), window_s=window or 60.0))
            mode = "on_event"
            if not source: source = "logs"

        # Detect audio conditions
        if re.search(r'\bspeech\b|\bvoice\b|\btalking\b|\bspoken\b', d):
            events.append(EventCondition(type="speech", threshold=0.5,
                                         min_duration_s=duration_s or 0.5))
            mode = "on_event"
            if not source: source = "audio"

        if re.search(r'\bloud\b|\bnoise\b|\bsound\s*level\b|\baudio\s*level\b', d):
            threshold = self._extract_float(d, r'(?:level|above|threshold)\s*(\d+(?:\.\d+)?)', 0.3)
            events.append(EventCondition(type="audio_level", threshold=threshold))
            mode = "on_event"
            if not source: source = "audio"

        # Determine mode based on combination
        if events and (fallback_s or periodic_s):
            mode = "hybrid" if periodic_s else "on_event"

        # Build rule
        if events or periodic_s:
            name_parts = []
            if events:
                name_parts.append(events[0].type)
                if events[0].label:
                    name_parts.append(events[0].label)
            name_parts.append(mode.replace("_", "-"))
            name = "-".join(name_parts) or "trigger"

            rule = TriggerRule(
                name=name,
                source=source,
                mode=mode,
                events=events,
                interval_s=periodic_s if periodic_s else (fallback_s if fallback_s else 30.0),
                fallback=FallbackConfig(periodic_s=fallback_s) if fallback_s else FallbackConfig(),
                goal=goal,
                cooldown_s=min(duration_s or 2.0, 10.0),
            )
            rules.append(rule)

        if rules:
            return TriggerConfig(triggers=rules)
        return None

    # ── LLM-based generation ──────────────────────────────────

    async def _generate_via_llm(self, description: str, source: str, goal: str) -> str:
        """Use LLM to generate YAML from description."""
        try:
            import litellm

            prompt = f"Source type: {source or 'auto-detect'}\nGoal: {goal or 'auto-detect'}\n\nUser description:\n{description}"

            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": YAML_SCHEMA_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                api_key=self.api_key or None,
            )

            text = response.choices[0].message.content.strip()

            # Extract YAML from markdown code block
            if "```" in text:
                m = re.search(r'```(?:yaml)?\s*\n?(.*?)\n?```', text, re.DOTALL)
                if m:
                    text = m.group(1).strip()

            # Validate it starts with triggers:
            if not text.startswith("triggers:"):
                text = "triggers:\n" + text

            return text

        except ImportError:
            logger.warning("litellm not available for NLP2YAML")
            return ""
        except Exception as e:
            logger.error(f"NLP2YAML LLM error: {e}")
            return ""

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _extract_time(text: str, pattern: str) -> float:
        """Extract time value from text, converting to seconds."""
        m = re.search(pattern, text)
        if not m:
            return 0.0
        val = float(m.group(1))
        unit = m.group(2).lower() if m.lastindex >= 2 else "s"
        if unit.startswith("m"):
            return val * 60
        elif unit.startswith("h"):
            return val * 3600
        return val

    @staticmethod
    def _extract_float(text: str, pattern: str, default: float = 0.0) -> float:
        m = re.search(pattern, text)
        return float(m.group(1)) if m else default
