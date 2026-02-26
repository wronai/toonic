"""
Tests for toonic.server.triggers — DSL, detectors, scheduler, NLP2YAML.
"""

import asyncio
import time

import pytest

from toonic.server.triggers.dsl import (
    TriggerConfig, TriggerRule, EventCondition, FallbackConfig,
    load_triggers, dump_triggers,
)
from toonic.server.triggers.detectors import (
    MotionDetector, SceneChangeDetector, ObjectDetector,
    AudioLevelDetector, SpeechDetector, PatternDetector, AnomalyDetector,
    create_detector, create_detectors, DetectionResult,
)
from toonic.server.triggers.scheduler import TriggerScheduler, TriggerEvent, RuleState
from toonic.server.triggers.nlp2yaml import NLP2YAML


# =============================================================================
# DSL tests
# =============================================================================

class TestDSL:
    def test_event_condition_roundtrip(self):
        ec = EventCondition(type="object", label="person", threshold=0.5, min_duration_s=1.0)
        d = ec.to_dict()
        assert d["type"] == "object"
        assert d["label"] == "person"
        ec2 = EventCondition.from_dict(d)
        assert ec2.label == "person"
        assert ec2.min_duration_s == 1.0

    def test_trigger_rule_roundtrip(self):
        rule = TriggerRule(
            name="test-rule",
            source="video",
            mode="hybrid",
            events=[EventCondition(type="motion", threshold=0.2)],
            fallback=FallbackConfig(periodic_s=60),
            interval_s=30,
            goal="test goal",
        )
        d = rule.to_dict()
        assert d["name"] == "test-rule"
        assert d["mode"] == "hybrid"
        assert len(d["events"]) == 1
        assert d["fallback"]["periodic_s"] == 60

        rule2 = TriggerRule.from_dict(d)
        assert rule2.name == "test-rule"
        assert rule2.fallback.periodic_s == 60
        assert len(rule2.events) == 1

    def test_trigger_config_roundtrip(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="r1", mode="periodic", interval_s=10),
            TriggerRule(name="r2", mode="on_event",
                        events=[EventCondition(type="pattern", regex="ERROR")]),
        ])
        d = cfg.to_dict()
        assert len(d["triggers"]) == 2

        cfg2 = TriggerConfig.from_dict(d)
        assert len(cfg2.triggers) == 2
        assert cfg2.triggers[0].name == "r1"

    def test_load_dump_yaml(self):
        yaml_str = """
triggers:
  - name: motion-alert
    source: video
    mode: on_event
    events:
      - type: motion
        threshold: 0.15
        min_duration_s: 2.0
    fallback:
      periodic_s: 60
    goal: "detect motion"
"""
        cfg = load_triggers(yaml_str)
        assert len(cfg.triggers) == 1
        assert cfg.triggers[0].name == "motion-alert"
        assert cfg.triggers[0].events[0].threshold == 0.15
        assert cfg.triggers[0].fallback.periodic_s == 60

        out = dump_triggers(cfg)
        assert "motion-alert" in out
        assert "motion" in out

    def test_get_rules_for_source(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="video-r", source="video"),
            TriggerRule(name="log-r", source="logs"),
            TriggerRule(name="all-r", source=""),
        ])
        video_rules = cfg.get_rules_for_source("video")
        assert len(video_rules) == 2  # video-r + all-r
        log_rules = cfg.get_rules_for_source("logs")
        assert len(log_rules) == 2  # log-r + all-r


# =============================================================================
# Detector tests
# =============================================================================

class TestDetectors:
    def test_motion_detector(self):
        cond = EventCondition(type="motion", threshold=0.2)
        det = MotionDetector(cond)

        r = det.evaluate({"scene_score": 0.1})
        assert not r.triggered

        r = det.evaluate({"scene_score": 0.5})
        assert r.triggered
        assert r.score == 0.5

    def test_motion_detector_with_duration(self):
        cond = EventCondition(type="motion", threshold=0.1, min_duration_s=0.1)
        det = MotionDetector(cond)

        r = det.evaluate({"scene_score": 0.5})
        assert not r.triggered  # first detection, duration not met

        time.sleep(0.15)
        r = det.evaluate({"scene_score": 0.5})
        assert r.triggered  # duration met

    def test_scene_change_detector(self):
        cond = EventCondition(type="scene_change", threshold=0.4)
        det = SceneChangeDetector(cond)

        assert not det.evaluate({"scene_score": 0.2}).triggered
        assert det.evaluate({"scene_score": 0.6}).triggered

    def test_object_detector_with_match(self):
        cond = EventCondition(type="object", label="person", threshold=0.3)
        det = ObjectDetector(cond)

        r = det.evaluate({"detected_objects": [
            {"label": "person", "confidence": 0.8, "size_pct": 20.0},
        ]})
        assert r.triggered
        assert r.label == "person"

    def test_object_detector_no_match(self):
        cond = EventCondition(type="object", label="car", threshold=0.5)
        det = ObjectDetector(cond)

        r = det.evaluate({"detected_objects": [
            {"label": "person", "confidence": 0.9},
        ]})
        assert not r.triggered

    def test_object_detector_size_filter(self):
        cond = EventCondition(type="object", label="person", threshold=0.3, min_size_pct=10.0)
        det = ObjectDetector(cond)

        r = det.evaluate({"detected_objects": [
            {"label": "person", "confidence": 0.8, "size_pct": 5.0},
        ]})
        assert not r.triggered  # too small

        r = det.evaluate({"detected_objects": [
            {"label": "person", "confidence": 0.8, "size_pct": 15.0},
        ]})
        assert r.triggered

    def test_audio_level_detector(self):
        cond = EventCondition(type="audio_level", threshold=0.5)
        det = AudioLevelDetector(cond)

        assert not det.evaluate({"audio_level": 0.2}).triggered
        assert det.evaluate({"audio_level": 0.7}).triggered

    def test_speech_detector(self):
        cond = EventCondition(type="speech", threshold=0.5)
        det = SpeechDetector(cond)

        assert not det.evaluate({"has_speech": False}).triggered
        assert det.evaluate({"has_speech": True}).triggered

    def test_pattern_detector(self):
        cond = EventCondition(type="pattern", regex="ERROR|CRITICAL", count_threshold=2, window_s=10)
        det = PatternDetector(cond)

        r = det.evaluate({"text": "INFO: all good"})
        assert not r.triggered

        r = det.evaluate({"text": "ERROR: something broke"})
        assert not r.triggered  # only 1 match, need 2

        r = det.evaluate({"text": "CRITICAL: system down"})
        assert r.triggered  # 2 matches within window

    def test_anomaly_detector(self):
        cond = EventCondition(type="anomaly", threshold=2.0)
        det = AnomalyDetector(cond)

        # Build baseline
        for v in [10, 11, 10, 9, 10, 11, 10]:
            det.evaluate({"value": v})

        # Normal value
        r = det.evaluate({"value": 10})
        assert not r.triggered

        # Anomalous value
        r = det.evaluate({"value": 100})
        assert r.triggered
        assert r.score > 2.0

    def test_negate(self):
        cond = EventCondition(type="motion", threshold=0.2, negate=True)
        det = MotionDetector(cond)

        r = det.evaluate({"scene_score": 0.5})
        assert not r.triggered  # motion detected but negated

        r = det.evaluate({"scene_score": 0.05})
        assert r.triggered  # no motion, negated = triggered

    def test_create_detector_factory(self):
        for t in ["motion", "scene_change", "object", "audio_level", "speech", "pattern", "anomaly"]:
            cond = EventCondition(type=t, regex="test" if t == "pattern" else "")
            det = create_detector(cond)
            assert det is not None

    def test_create_detectors_list(self):
        conditions = [
            EventCondition(type="motion", threshold=0.2),
            EventCondition(type="scene_change", threshold=0.4),
        ]
        dets = create_detectors(conditions)
        assert len(dets) == 2


# =============================================================================
# Scheduler tests
# =============================================================================

class TestScheduler:
    def test_periodic_mode(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="periodic", mode="periodic", interval_s=0.05, cooldown_s=0.01),
        ])
        sched = TriggerScheduler(cfg)

        # First eval: last_periodic=0, so elapsed is huge -> fires immediately
        events = sched.evaluate({}, "video")
        assert len(events) == 1
        assert events[0].reason == "periodic"

        # Second eval immediately: interval not reached
        events = sched.evaluate({}, "video")
        assert len(events) == 0

        # After interval (with margin)
        time.sleep(0.1)
        events = sched.evaluate({}, "video")
        assert len(events) == 1
        assert events[0].reason == "periodic"

    def test_on_event_mode(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="motion", mode="on_event",
                        events=[EventCondition(type="motion", threshold=0.2)]),
        ])
        sched = TriggerScheduler(cfg)

        events = sched.evaluate({"scene_score": 0.05}, "video")
        assert len(events) == 0

        events = sched.evaluate({"scene_score": 0.5}, "video")
        assert len(events) == 1
        assert events[0].reason == "event"

    def test_on_event_with_fallback(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="motion-fb", mode="on_event",
                        events=[EventCondition(type="motion", threshold=0.9)],
                        fallback=FallbackConfig(periodic_s=0.1),
                        cooldown_s=0.01),
        ])
        sched = TriggerScheduler(cfg)

        # First eval: last_triggered=0, so fallback fires immediately
        events = sched.evaluate({"scene_score": 0.1}, "video")
        assert len(events) == 1
        assert events[0].reason == "fallback"

        # Immediately again: cooldown
        events = sched.evaluate({"scene_score": 0.1}, "video")
        assert len(events) == 0

        time.sleep(0.15)
        events = sched.evaluate({"scene_score": 0.1}, "video")
        assert len(events) == 1
        assert events[0].reason == "fallback"

    def test_hybrid_mode(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="hybrid", mode="hybrid",
                        events=[EventCondition(type="motion", threshold=0.3)],
                        interval_s=0.1, cooldown_s=0.01),
        ])
        sched = TriggerScheduler(cfg)

        # Event triggers immediately
        events = sched.evaluate({"scene_score": 0.5}, "video")
        assert len(events) == 1
        assert events[0].reason == "event"

    def test_source_filter(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="video-only", source="video", mode="periodic", interval_s=0.01),
        ])
        sched = TriggerScheduler(cfg)

        events = sched.evaluate({}, "logs")
        assert len(events) == 0  # wrong source

        events = sched.evaluate({}, "video")
        assert len(events) == 1  # correct source

    def test_cooldown(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="cd", mode="on_event",
                        events=[EventCondition(type="motion", threshold=0.1)],
                        cooldown_s=1.0),
        ])
        sched = TriggerScheduler(cfg)

        events = sched.evaluate({"scene_score": 0.5}, "video")
        assert len(events) == 1

        events = sched.evaluate({"scene_score": 0.5}, "video")
        assert len(events) == 0  # cooldown

    def test_add_remove_rule(self):
        sched = TriggerScheduler(TriggerConfig())
        assert sched.get_stats()["total_rules"] == 0

        sched.add_rule(TriggerRule(name="new", mode="periodic", interval_s=1))
        assert sched.get_stats()["total_rules"] == 1

        sched.remove_rule("new")
        assert sched.get_stats()["total_rules"] == 0

    def test_default_periodic(self):
        sched = TriggerScheduler.default_periodic(interval_s=5.0, goal="test")
        assert sched.get_stats()["total_rules"] == 1

    @pytest.mark.anyio
    async def test_evaluate_async_with_callback(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="cb-test", mode="on_event",
                        events=[EventCondition(type="motion", threshold=0.1)]),
        ])
        sched = TriggerScheduler(cfg)

        fired = []
        async def callback(event):
            fired.append(event)
        sched.on_trigger(callback)

        await sched.evaluate_async({"scene_score": 0.5}, "video")
        assert len(fired) == 1
        assert fired[0].rule_name == "cb-test"

    def test_from_yaml(self):
        yaml_str = """
triggers:
  - name: test
    mode: periodic
    interval_s: 5
"""
        sched = TriggerScheduler.from_yaml(yaml_str)
        assert sched.get_stats()["total_rules"] == 1

    def test_event_logic_all(self):
        cfg = TriggerConfig(triggers=[
            TriggerRule(name="all-logic", mode="on_event", event_logic="all",
                        events=[
                            EventCondition(type="motion", threshold=0.2),
                            EventCondition(type="scene_change", threshold=0.3),
                        ]),
        ])
        sched = TriggerScheduler(cfg)

        # Only motion met
        events = sched.evaluate({"scene_score": 0.25}, "video")
        assert len(events) == 0  # scene_change not met

        # Both met
        events = sched.evaluate({"scene_score": 0.5}, "video")
        assert len(events) == 1


# =============================================================================
# NLP2YAML tests
# =============================================================================

class TestNLP2YAML:
    def test_parse_person_detected(self):
        nlp = NLP2YAML()
        config = nlp._try_local_parse(
            "the object person will be detected for 1 second on the frame, if not send frame min. every 1 minute",
            source="video", goal="describe people"
        )
        assert config is not None
        assert len(config.triggers) == 1
        rule = config.triggers[0]
        assert any(e.type == "object" and e.label == "person" for e in rule.events)
        assert any(e.min_duration_s == 1.0 for e in rule.events)
        assert rule.fallback.periodic_s == 60.0

    def test_parse_every_n_seconds(self):
        nlp = NLP2YAML()
        config = nlp._try_local_parse("every 10 seconds", source="video")
        assert config is not None
        rule = config.triggers[0]
        assert rule.interval_s == 10.0

    def test_parse_motion_detection(self):
        nlp = NLP2YAML()
        config = nlp._try_local_parse("when motion detected, otherwise every 2 minutes")
        assert config is not None
        rule = config.triggers[0]
        assert any(e.type == "motion" for e in rule.events)
        assert rule.fallback.periodic_s == 120.0

    def test_parse_error_pattern(self):
        nlp = NLP2YAML()
        config = nlp._try_local_parse("when error occurs 5 times in 60 seconds")
        assert config is not None
        rule = config.triggers[0]
        assert any(e.type == "pattern" for e in rule.events)
        assert any(e.count_threshold == 5 for e in rule.events)

    def test_parse_scene_change(self):
        nlp = NLP2YAML()
        config = nlp._try_local_parse("on scene change, otherwise every 30 seconds")
        assert config is not None
        rule = config.triggers[0]
        assert any(e.type == "scene_change" for e in rule.events)

    def test_parse_speech_detection(self):
        nlp = NLP2YAML()
        config = nlp._try_local_parse("when speech detected for 2 seconds")
        assert config is not None
        rule = config.triggers[0]
        assert any(e.type == "speech" for e in rule.events)
        assert rule.source == "audio"

    def test_generate_yaml_output(self):
        nlp = NLP2YAML()
        yaml_str = nlp.generate_yaml("every 15 seconds", source="video", goal="test")
        assert yaml_str != ""
        assert "triggers:" in yaml_str

    @pytest.mark.anyio
    async def test_generate_fallback(self):
        nlp = NLP2YAML()
        config = await nlp.generate("something completely unparseable xyz123", goal="test")
        assert config is not None
        assert len(config.triggers) >= 1  # should fallback to default

    def test_extract_time_seconds(self):
        assert NLP2YAML._extract_time("every 10 seconds", r'every\s+(\d+)\s*(s)') == 10.0
        assert NLP2YAML._extract_time("every 2 minutes", r'every\s+(\d+)\s*(m)') == 120.0
        assert NLP2YAML._extract_time("every 1 hour", r'every\s+(\d+)\s*(h)') == 3600.0

    def test_the_exact_user_example(self):
        """Test the exact --when parameter from user's request."""
        nlp = NLP2YAML()
        desc = "the object person will be detected for 1 second on the frame, if not send frame min. every 1 minute"
        config = nlp._try_local_parse(desc, source="video",
                                       goal="describe what you see in each video frame")
        assert config is not None
        rule = config.triggers[0]
        # Must have object/person event
        obj_events = [e for e in rule.events if e.type == "object"]
        assert len(obj_events) == 1
        assert obj_events[0].label == "person"
        assert obj_events[0].min_duration_s == 1.0
        # Must have 60s fallback
        assert rule.fallback.periodic_s == 60.0
        assert rule.goal == "describe what you see in each video frame"
