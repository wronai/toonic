"""Tests for protocol detection across CLI parser, quick parser, and watcher registry.

Covers 20 popular protocols:
  Supported:   http, https, ws, wss, grpc, rtsp, rtsps, rtmp,
               postgresql, postgres, mysql, redis, mongodb
  Unsupported: ftp, sftp, ssh, mqtt, amqp, kafka, nats, stomp, ldap
"""

import pytest


def _parse(src: str):
    from toonic.server.__main__ import parse_source_string
    return parse_source_string(src)


def _quick(src: str):
    from toonic.server.quick import parse_source
    return parse_source(src)


# ── 13 supported protocols ────────────────────────────────────────

class TestSupportedProtocols:
    """Protocols that have matching watchers."""

    @pytest.mark.parametrize(
        "src,expected_cat",
        [
            # HttpWatcher
            ("http://example.com", "web"),
            ("https://example.com", "web"),
            ("ws://example.com/ws", "api"),
            ("wss://example.com/ws", "api"),
            ("grpc://example.com:50051", "api"),
            # StreamWatcher
            ("rtsp://cam:554/stream", "video"),
            ("rtsps://cam:322/stream", "video"),
            ("rtmp://live.example.com/app/key", "video"),
            # DatabaseWatcher
            ("postgresql://user:pass@db:5432/mydb", "database"),
            ("postgres://user:pass@db:5432/mydb", "database"),
            ("mysql://user:pass@db:3306/mydb", "database"),
            ("redis://cache:6379", "database"),
            ("mongodb://db:27017/mydb", "database"),
        ],
    )
    def test_cli_parser_category(self, src, expected_cat):
        cfg = _parse(src)
        assert cfg.category == expected_cat, f"{src} -> {cfg.category} (expected {expected_cat})"
        assert cfg.path_or_url.startswith(src.split("://")[0])

    @pytest.mark.parametrize(
        "src,expected_cat",
        [
            ("http://example.com", "web"),
            ("https://example.com", "web"),
            ("ws://example.com/ws", "api"),
            ("wss://example.com/ws", "api"),
            ("grpc://example.com:50051", "api"),
            ("rtsp://cam:554/stream", "video"),
            ("rtsps://cam:322/stream", "video"),
            ("rtmp://live.example.com/app/key", "video"),
            ("postgresql://user:pass@db:5432/mydb", "database"),
            ("mysql://user:pass@db:3306/mydb", "database"),
            ("redis://cache:6379", "database"),
            ("mongodb://db:27017/mydb", "database"),
        ],
    )
    def test_quick_parser_category(self, src, expected_cat):
        cfg = _quick(src)
        assert cfg.category == expected_cat, f"{src} -> {cfg.category} (expected {expected_cat})"

    @pytest.mark.parametrize(
        "src,expected_cat",
        [
            ("http://example.com", "web"),
            ("https://example.com", "web"),
            ("ws://example.com/ws", "api"),
            ("wss://example.com/ws", "api"),
            ("grpc://example.com:50051", "api"),
            ("rtsp://cam:554/stream", "video"),
            ("rtsps://cam:322/stream", "video"),
            ("rtmp://live.example.com/app/key", "video"),
        ],
    )
    def test_cli_and_quick_agree_on_category(self, src, expected_cat):
        cli_cfg = _parse(src)
        quick_cfg = _quick(src)
        assert cli_cfg.category == quick_cfg.category, (
            f"CLI={cli_cfg.category}, quick={quick_cfg.category} for {src}"
        )


# ── 10 unsupported protocols ──────────────────────────────────────

class TestUnsupportedProtocols:
    """Protocols without watchers — should fail fast with clear error."""

    @pytest.mark.parametrize(
        "src",
        [
            "ftp://files.example.com/data.csv",
            "sftp://server/path",
            "ssh://server",
            "mqtt://broker:1883/topic",
            "amqp://mq:5672/vhost",
            "kafka://broker:9092/topic",
            "nats://server:4222",
            "stomp://mq:61613",
            "ldap://dc.example.com",
        ],
    )
    def test_cli_raises_for_unsupported(self, src):
        with pytest.raises(ValueError, match="not supported"):
            _parse(src)

    @pytest.mark.parametrize(
        "src,expected_cat",
        [
            ("ftp://files.example.com", "data"),
            ("sftp://server/path", "data"),
            ("ssh://server", "infra"),
            ("mqtt://broker:1883", "data"),
            ("amqp://mq:5672", "data"),
            ("kafka://broker:9092", "data"),
            ("nats://server:4222", "data"),
            ("ldap://dc.example.com", "network"),
        ],
    )
    def test_quick_still_maps_category(self, src, expected_cat):
        """quick.parse_source maps even unsupported protocols to a category."""
        cfg = _quick(src)
        assert cfg.category == expected_cat


# ── Prefix-based sources ──────────────────────────────────────────

class TestPrefixSources:

    @pytest.mark.parametrize(
        "src,expected_path",
        [
            ("file:./src/", "./src/"),
            ("code:./src/", "./src/"),
            ("config:./settings.yaml", "./settings.yaml"),
            ("data:./metrics.csv", "./metrics.csv"),
            ("doc:./README.md", "./README.md"),
        ],
    )
    def test_file_like_prefixes_normalized_to_path(self, src, expected_path):
        cfg = _parse(src)
        assert cfg.path_or_url == expected_path

    @pytest.mark.parametrize(
        "src",
        [
            "log:./app.log",
            "dir:./data/",
            "docker:*",
            "db:./app.db",
            "net:8.8.8.8",
            "proc:nginx",
            "pid:1234",
            "port:8080",
            "tcp:db:5432",
            "service:postgresql",
        ],
    )
    def test_watcher_prefixes_preserved(self, src):
        cfg = _parse(src)
        assert cfg.path_or_url == src

    def test_plain_path(self):
        cfg = _parse("./src/")
        assert cfg.category == "code"
        assert cfg.path_or_url == "./src/"


# ── Watcher resolution ────────────────────────────────────────────

class TestWatcherResolution:
    """Verify WatcherRegistry.resolve picks the correct watcher class."""

    @pytest.mark.parametrize(
        "url,expected_watcher",
        [
            ("http://example.com", "HttpWatcher"),
            ("https://example.com", "HttpWatcher"),
            ("ws://example.com/ws", "HttpWatcher"),
            ("wss://example.com/ws", "HttpWatcher"),
            ("grpc://example.com:50051", "HttpWatcher"),
            ("rtsp://cam:554/stream", "StreamWatcher"),
            ("rtsps://cam:322/stream", "StreamWatcher"),
            ("rtmp://live.example.com/app/key", "StreamWatcher"),
        ],
    )
    def test_resolve_picks_correct_watcher(self, url, expected_watcher):
        from toonic.server.watchers.base import WatcherRegistry
        cls = WatcherRegistry.resolve(url)
        assert cls is not None, f"No watcher resolved for {url}"
        assert cls.__name__ == expected_watcher, f"{url} -> {cls.__name__} (expected {expected_watcher})"


# ── Prompt builder selection ──────────────────────────────────────

class TestPromptBuilderForProtocols:
    """Web/API sources must use GenericPrompt, not CodeAnalysisPrompt."""

    def test_web_source_uses_generic_prompt(self):
        from toonic.server.llm.prompts import select_prompt_builder, GenericPrompt, CodeAnalysisPrompt
        from toonic.server.models import SourceCategory
        builder = select_prompt_builder("describe what you see", {SourceCategory.WEB})
        assert isinstance(builder, GenericPrompt)
        assert not isinstance(builder, CodeAnalysisPrompt)

    def test_api_source_uses_generic_prompt(self):
        from toonic.server.llm.prompts import select_prompt_builder, GenericPrompt
        from toonic.server.models import SourceCategory
        builder = select_prompt_builder("monitor API health", {SourceCategory.API})
        assert isinstance(builder, GenericPrompt)

    def test_network_source_uses_generic_prompt(self):
        from toonic.server.llm.prompts import select_prompt_builder, GenericPrompt
        from toonic.server.models import SourceCategory
        builder = select_prompt_builder("check connectivity", {SourceCategory.NETWORK})
        assert isinstance(builder, GenericPrompt)

    def test_code_source_uses_code_prompt(self):
        from toonic.server.llm.prompts import select_prompt_builder, CodeAnalysisPrompt
        from toonic.server.models import SourceCategory
        builder = select_prompt_builder("find bugs", {SourceCategory.CODE})
        assert isinstance(builder, CodeAnalysisPrompt)

    def test_empty_categories_with_code_goal_uses_code_prompt(self):
        from toonic.server.llm.prompts import select_prompt_builder, CodeAnalysisPrompt
        builder = select_prompt_builder("analyze code quality", set())
        assert isinstance(builder, CodeAnalysisPrompt)

    def test_empty_categories_with_generic_goal_uses_generic(self):
        from toonic.server.llm.prompts import select_prompt_builder, GenericPrompt
        builder = select_prompt_builder("describe what you see", set())
        assert isinstance(builder, GenericPrompt)
