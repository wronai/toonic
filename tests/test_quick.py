"""Tests for toonic.server.quick — ConfigBuilder, parse_source, watch()."""

import tarfile
import zipfile
from pathlib import Path

import pytest
from toonic.server.quick import (
    ConfigBuilder,
    parse_source,
    unpack_archive,
    watch_archive,
    watch,
)
from toonic.server.config import ServerConfig, SourceConfig


# ══════════════════════════════════════════════════════════════
# parse_source
# ══════════════════════════════════════════════════════════════

class TestParseSource:
    """Tests for the universal source parser."""

    def test_passthrough_source_config(self):
        src = SourceConfig(path_or_url="./x", category="logs")
        assert parse_source(src) is src

    def test_dict_source(self):
        src = parse_source({"path_or_url": "./app.log", "category": "logs"})
        assert src.path_or_url == "./app.log"
        assert src.category == "logs"

    # ── Prefix detection ──

    @pytest.mark.parametrize("input_str,expected_cat", [
        ("log:./app.log", "logs"),
        ("logs:./err.log", "logs"),
        ("code:./src/", "code"),
        ("file:./main.py", "code"),
        ("src:./lib/", "code"),
        ("config:./settings.yaml", "config"),
        ("cfg:./app.ini", "config"),
        ("data:./metrics.csv", "data"),
        ("csv:./data.csv", "data"),
        ("json:./events.json", "data"),
        ("doc:./readme.md", "document"),
        ("docker:*", "container"),
        ("docker:my-app", "container"),
        ("container:web", "container"),
        ("db:./app.db", "database"),
        ("sqlite:./data.sqlite", "database"),
        ("postgres:localhost", "database"),
        ("postgresql:localhost", "database"),
        ("mysql:localhost", "database"),
        ("net:8.8.8.8", "network"),
        ("ping:google.com", "network"),
        ("dns:cloudflare.com", "network"),
        ("proc:nginx", "process"),
        ("pid:1234", "process"),
        ("port:8080", "process"),
        ("tcp:db:5432", "process"),
        ("service:postgresql", "process"),
        ("dir:./data/", "infra"),
    ])
    def test_prefix_detection(self, input_str, expected_cat):
        src = parse_source(input_str)
        assert src.category == expected_cat

    # ── Protocol URL detection ──

    @pytest.mark.parametrize("url,expected_cat", [
        ("rtsp://192.168.1.1:554/stream", "video"),
        ("http://api.example.com/health", "web"),
        ("https://api.example.com/v2", "web"),
        ("postgresql://user:pass@db:5432/mydb", "database"),
        ("redis://cache:6379", "database"),
        ("mqtt://broker:1883/topic", "data"),
    ])
    def test_protocol_detection(self, url, expected_cat):
        src = parse_source(url)
        assert src.path_or_url == url
        assert src.category == expected_cat

    # ── Extension detection (plain paths) ──

    @pytest.mark.parametrize("path,expected_cat", [
        ("./app.log", "logs"),
        ("./data.db", "database"),
        ("./data.sqlite3", "database"),
        ("./metrics.csv", "data"),
        ("./events.jsonl", "data"),
        ("./config.yaml", "config"),
        ("./config.toml", "config"),
        ("./readme.md", "document"),
        ("./video.mp4", "video"),
        ("./audio.wav", "audio"),
        ("./src/main.py", "code"),
        ("./bundle.zip", "data"),
        ("./bundle.tar", "data"),
        ("./bundle.tar.gz", "data"),
    ])
    def test_extension_detection(self, path, expected_cat):
        src = parse_source(path)
        assert src.category == expected_cat

    def test_plain_directory_defaults_to_code(self):
        src = parse_source("./src/")
        assert src.category == "code"


# ══════════════════════════════════════════════════════════════
# Archive helpers
# ══════════════════════════════════════════════════════════════


class TestArchiveHelpers:
    def test_unpack_archive_zip(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("hello", encoding="utf-8")

        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(src_dir / "a.txt", arcname="a.txt")

        out_dir = unpack_archive(str(zip_path))
        assert Path(out_dir).exists()
        assert (Path(out_dir) / "a.txt").read_text(encoding="utf-8") == "hello"

    def test_unpack_archive_tar_gz(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("hello", encoding="utf-8")

        tar_path = tmp_path / "bundle.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(src_dir / "a.txt", arcname="a.txt")

        out_dir = unpack_archive(str(tar_path))
        assert Path(out_dir).exists()
        assert (Path(out_dir) / "a.txt").read_text(encoding="utf-8") == "hello"

    def test_watch_archive_returns_builder(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(tmp_path / "a.txt", arcname="a.txt")

        b = watch_archive(str(zip_path), include_files_as_sources=True)
        assert isinstance(b, ConfigBuilder)
        assert len(b._sources) >= 2



# ══════════════════════════════════════════════════════════════
# ConfigBuilder
# ══════════════════════════════════════════════════════════════

class TestConfigBuilder:
    """Tests for fluent ConfigBuilder."""

    def test_basic_build_config(self):
        cfg = (
            ConfigBuilder()
            .add("./src/")
            .add("log:./app.log")
            .goal("find bugs")
            .interval(60)
            .port(9000)
            .build_config()
        )
        assert isinstance(cfg, ServerConfig)
        assert cfg.goal == "find bugs"
        assert cfg.interval == 60.0
        assert cfg.port == 9000
        assert len(cfg.sources) == 2

    def test_typed_source_methods(self):
        builder = ConfigBuilder()
        builder.code("./src/")
        builder.logs("./app.log")
        builder.docker("*")
        builder.database("db:./app.db")
        builder.network("8.8.8.8,1.1.1.1")
        builder.process("proc:nginx")
        builder.http("https://api.example.com")
        builder.directory("./data/")

        cfg = builder.build_config()
        categories = [s.category for s in cfg.sources]
        assert "code" in categories
        assert "logs" in categories
        assert "container" in categories
        assert "database" in categories
        assert "network" in categories
        assert "process" in categories
        assert "api" in categories
        assert "infra" in categories

    def test_model_override(self):
        cfg = ConfigBuilder().add("./src/").model("gpt-4").build_config()
        for m in cfg.models.values():
            assert m.model == "gpt-4"

    def test_token_allocation(self):
        alloc = {"code": 0.5, "logs": 0.3, "system": 0.2}
        cfg = ConfigBuilder().add("./src/").tokens(50000, alloc).build_config()
        assert cfg.max_context_tokens == 50000
        assert cfg.token_allocation == alloc

    def test_no_history(self):
        cfg = ConfigBuilder().add("./src/").no_history().build_config()
        assert cfg.history_enabled is False

    def test_log_level(self):
        cfg = ConfigBuilder().add("./src/").log_level("DEBUG").build_config()
        assert cfg.log_level == "DEBUG"

    def test_add_with_options(self):
        builder = ConfigBuilder()
        builder.add("log:./app.log", poll_interval=5, max_lines=1000)
        src = builder._sources[0]
        assert src.options["poll_interval"] == "5"
        assert src.options["max_lines"] == "1000"

    def test_chaining(self):
        """Verify all methods return self for chaining."""
        b = ConfigBuilder()
        result = (
            b.add("./src/")
            .code("./lib/")
            .logs("./app.log")
            .video("rtsp://cam:554/stream")
            .docker("*")
            .database("db:./app.db")
            .network("8.8.8.8")
            .process("proc:nginx")
            .http("https://api.example.com")
            .directory("./data/")
            .goal("test")
            .interval(10)
            .model("gpt-4")
            .port(9000)
            .host("127.0.0.1")
            .tokens(50000)
            .when("error occurs")
            .triggers("./triggers.yaml")
            .no_web()
            .no_history()
            .log_level("DEBUG")
        )
        assert result is b

    def test_build_server(self):
        """Build returns a ToonicServer instance."""
        from toonic.server.main import ToonicServer
        srv = ConfigBuilder().add("./src/").goal("test").build()
        assert isinstance(srv, ToonicServer)
        assert srv.config.goal == "test"


# ══════════════════════════════════════════════════════════════
# watch() helper
# ══════════════════════════════════════════════════════════════

class TestWatch:
    """Tests for the watch() convenience function."""

    def test_watch_returns_builder(self):
        b = watch("./src/")
        assert isinstance(b, ConfigBuilder)
        assert len(b._sources) == 1

    def test_watch_multiple_sources(self):
        b = watch("./src/", "log:./app.log", "docker:*")
        assert len(b._sources) == 3

    def test_watch_mixed_types(self):
        b = watch(
            "./src/",
            SourceConfig(path_or_url="./app.log", category="logs"),
            {"path_or_url": "docker:*", "category": "container"},
        )
        assert len(b._sources) == 3
        cats = [s.category for s in b._sources]
        assert "code" in cats
        assert "logs" in cats
        assert "container" in cats

    def test_watch_chain_to_build(self):
        """Full chain: watch → config → server."""
        from toonic.server.main import ToonicServer
        srv = (
            watch("./src/", "log:./app.log")
            .goal("test")
            .interval(10)
            .build()
        )
        assert isinstance(srv, ToonicServer)
        assert len(srv.config.sources) == 2


# ══════════════════════════════════════════════════════════════
# Presets
# ══════════════════════════════════════════════════════════════

class TestPresets:
    """Tests for pre-configured monitoring presets."""

    def test_security_audit_defaults(self):
        from toonic.server.quick import security_audit
        b = security_audit("./src/")
        cfg = b.build_config()
        assert "security" in cfg.goal.lower()
        assert cfg.interval == 0  # one-shot
        assert len(cfg.sources) == 1
        assert cfg.sources[0].category == "code"

    def test_security_audit_multi_source(self):
        from toonic.server.quick import security_audit
        b = security_audit("./src/", "log:./auth.log")
        cfg = b.build_config()
        assert len(cfg.sources) == 2

    def test_security_audit_override_goal(self):
        from toonic.server.quick import security_audit
        b = security_audit("./src/", goal="custom goal")
        cfg = b.build_config()
        assert cfg.goal == "custom goal"

    def test_code_review_defaults(self):
        from toonic.server.quick import code_review
        b = code_review("./src/")
        cfg = b.build_config()
        assert "code review" in cfg.goal.lower()
        assert cfg.interval == 0
        assert len(cfg.sources) == 1

    def test_code_review_override_interval(self):
        from toonic.server.quick import code_review
        b = code_review("./src/", interval=60)
        cfg = b.build_config()
        assert cfg.interval == 60

    def test_log_monitor_defaults(self):
        from toonic.server.quick import log_monitor
        b = log_monitor("log:./app.log")
        cfg = b.build_config()
        assert "log" in cfg.goal.lower()
        assert cfg.interval == 10
        assert cfg.sources[0].category == "logs"

    def test_infra_health_defaults(self):
        from toonic.server.quick import infra_health
        b = infra_health("docker:*", "net:8.8.8.8")
        cfg = b.build_config()
        assert "infrastructure" in cfg.goal.lower()
        assert cfg.interval == 30
        assert len(cfg.sources) == 2

    def test_cctv_monitor_defaults(self):
        from toonic.server.quick import cctv_monitor
        b = cctv_monitor("rtsp://cam:554/stream")
        cfg = b.build_config()
        assert "cctv" in cfg.goal.lower()
        assert cfg.sources[0].category == "video"

    def test_web_monitor_defaults(self):
        from toonic.server.quick import web_monitor
        b = web_monitor("https://example.com/health")
        cfg = b.build_config()
        assert "web" in cfg.goal.lower()
        assert cfg.interval == 60
        assert cfg.sources[0].category == "api"

    def test_web_monitor_multiple_urls(self):
        from toonic.server.quick import web_monitor
        b = web_monitor("https://a.com", "https://b.com", "https://c.com")
        cfg = b.build_config()
        assert len(cfg.sources) == 3

    def test_full_stack_defaults(self):
        from toonic.server.quick import full_stack
        b = full_stack("./src/", "log:./app.log", "docker:*")
        cfg = b.build_config()
        assert "full-stack" in cfg.goal.lower()
        assert cfg.interval == 30
        assert len(cfg.sources) == 3

    def test_preset_chaining(self):
        """Presets return ConfigBuilder — can chain further."""
        from toonic.server.quick import security_audit
        b = security_audit("./src/").network("8.8.8.8").process("port:5432")
        cfg = b.build_config()
        assert len(cfg.sources) == 3
        cats = [s.category for s in cfg.sources]
        assert "code" in cats
        assert "network" in cats
        assert "process" in cats

    def test_preset_no_sources(self):
        """Preset with no sources returns empty ConfigBuilder."""
        from toonic.server.quick import security_audit
        b = security_audit()
        cfg = b.build_config()
        assert len(cfg.sources) == 0
        assert "security" in cfg.goal.lower()

    def test_presets_registry(self):
        from toonic.server.quick import PRESETS
        assert len(PRESETS) == 7
        for name, info in PRESETS.items():
            assert "fn" in info
            assert "desc" in info
            assert callable(info["fn"])

    def test_presets_registry_all_build(self):
        """Every preset in PRESETS registry builds a valid config."""
        from toonic.server.quick import PRESETS
        for name, info in PRESETS.items():
            builder = info["fn"]("./src/")
            cfg = builder.build_config()
            assert cfg.goal, f"Preset {name} has empty goal"
            assert len(cfg.sources) >= 1, f"Preset {name} has no sources"
