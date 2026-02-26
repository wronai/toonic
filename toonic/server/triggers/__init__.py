"""
Trigger system — event-driven data dispatch to LLMs.

Supports:
- YAML DSL for declarative trigger configuration
- NLP2YAML for natural language → YAML generation via LLM
- Multiple trigger modes: periodic, on-event, hybrid
- Event detectors: motion, scene change, object presence, audio level, text patterns
"""

from toonic.server.triggers.dsl import TriggerConfig, TriggerRule, load_triggers, dump_triggers
from toonic.server.triggers.scheduler import TriggerScheduler
from toonic.server.triggers.nlp2yaml import NLP2YAML

__all__ = [
    "TriggerConfig", "TriggerRule", "load_triggers", "dump_triggers",
    "TriggerScheduler", "NLP2YAML",
]
