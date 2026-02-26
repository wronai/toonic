"""
Tests for new watchers — HTTP, Process, Directory, Docker, Database, Network.
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from toonic.server.models import ContextChunk, SourceCategory
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry
from toonic.server.watchers.http_watcher import HttpWatcher
from toonic.server.watchers.process_watcher import ProcessWatcher
from toonic.server.watchers.directory_watcher import DirectoryWatcher
from toonic.server.watchers.docker_watcher import DockerWatcher
from toonic.server.watchers.database_watcher import DatabaseWatcher
from toonic.server.watchers.network_watcher import NetworkWatcher


# =============================================================================
# WatcherRegistry — new watcher resolution tests
# =============================================================================

class TestWatcherRegistryNew:
    def test_http_watcher_supports(self):
        assert HttpWatcher.supports("http://example.com") > 0.5
        assert HttpWatcher.supports("https://api.example.com/health") > 0.5
        assert HttpWatcher.supports("web:http://example.com") > 0.9
        assert HttpWatcher.supports("/some/path") == 0.0

    def test_process_watcher_supports(self):
        assert ProcessWatcher.supports("proc:nginx") > 0.9
        assert ProcessWatcher.supports("pid:1234") > 0.9
        assert ProcessWatcher.supports("port:8080") > 0.9
        assert ProcessWatcher.supports("tcp:localhost:5432") > 0.9
        assert ProcessWatcher.supports("service:postgresql") > 0.9
        assert ProcessWatcher.supports("/some/path") == 0.0

    def test_directory_watcher_supports(self):
        assert DirectoryWatcher.supports("dir:/tmp") > 0.9
        assert DirectoryWatcher.supports("dir:/var/data") > 0.9
        assert DirectoryWatcher.supports("/some/path") == 0.0

    def test_docker_watcher_supports(self):
        assert DockerWatcher.supports("docker:myapp") > 0.9
        assert DockerWatcher.supports("docker:*") > 0.9
        assert DockerWatcher.supports("/some/path") == 0.0

    def test_database_watcher_supports(self):
        assert DatabaseWatcher.supports("db:test.db") > 0.9
        assert DatabaseWatcher.supports("sqlite:test.sqlite3") > 0.9
        assert DatabaseWatcher.supports("postgresql://localhost/mydb") > 0.8
        assert DatabaseWatcher.supports("test.db") > 0.8
        assert DatabaseWatcher.supports("/some/path") == 0.0

    def test_network_watcher_supports(self):
        assert NetworkWatcher.supports("net:8.8.8.8") > 0.9
        assert NetworkWatcher.supports("ping:google.com") > 0.9
        assert NetworkWatcher.supports("dns:example.com") > 0.9
        assert NetworkWatcher.supports("/some/path") == 0.0

    def test_registry_resolves_new_watchers(self):
        assert WatcherRegistry.resolve("http://example.com") == HttpWatcher
        assert WatcherRegistry.resolve("proc:nginx") == ProcessWatcher
        assert WatcherRegistry.resolve("dir:/tmp") == DirectoryWatcher
        assert WatcherRegistry.resolve("docker:myapp") == DockerWatcher
        assert WatcherRegistry.resolve("db:test.db") == DatabaseWatcher
        assert WatcherRegistry.resolve("net:8.8.8.8") == NetworkWatcher

    def test_registry_create_by_category(self):
        w = WatcherRegistry.create("test", "web", "http://example.com")
        assert isinstance(w, HttpWatcher)

        w = WatcherRegistry.create("test", "process", "proc:nginx")
        assert isinstance(w, ProcessWatcher)

        w = WatcherRegistry.create("test", "container", "docker:myapp")
        assert isinstance(w, DockerWatcher)

        w = WatcherRegistry.create("test", "database", "db:test.db")
        assert isinstance(w, DatabaseWatcher)

        w = WatcherRegistry.create("test", "network", "net:8.8.8.8")
        assert isinstance(w, NetworkWatcher)

    def test_all_watchers_registered(self):
        names = WatcherRegistry.list_all()
        assert "HttpWatcher" in names
        assert "ProcessWatcher" in names
        assert "DirectoryWatcher" in names
        assert "DockerWatcher" in names
        assert "DatabaseWatcher" in names
        assert "NetworkWatcher" in names
        assert len(names) == 9


# =============================================================================
# SourceCategory — new categories
# =============================================================================

class TestSourceCategoryNew:
    def test_new_categories_exist(self):
        assert SourceCategory.WEB == "web"
        assert SourceCategory.NETWORK == "network"
        assert SourceCategory.CONTAINER == "container"
        assert SourceCategory.PROCESS == "process"

    def test_all_categories(self):
        # Should have at least 14 categories
        assert len(SourceCategory) >= 14


# =============================================================================
# HttpWatcher tests
# =============================================================================

class TestHttpWatcher:
    def test_init(self):
        w = HttpWatcher("test:http", "http://example.com", poll_interval=60, timeout=5)
        assert w.poll_interval == 60.0
        assert w.timeout == 5.0
        assert w.method == "GET"
        assert w.expected_status == 200

    def test_init_with_options(self):
        w = HttpWatcher("test:http", "http://api.example.com",
                        method="POST", expected_status=201,
                        keywords=["success", "ok"],
                        check_ssl=False)
        assert w.method == "POST"
        assert w.expected_status == 201
        assert w.keywords == ["success", "ok"]
        assert w.check_ssl is False

    def test_to_toon(self):
        w = HttpWatcher("web:example", "http://example.com")
        w._check_count = 5
        result = {
            "status_code": 200,
            "response_time_ms": 150.5,
            "changes": ["content_changed"],
            "check_number": 5,
        }
        toon = w._to_toon(result)
        assert "web:example" in toon
        assert "http-check" in toon
        assert "200" in toon
        assert "content_changed" in toon

    def test_to_toon_with_error(self):
        w = HttpWatcher("web:example", "http://example.com")
        result = {
            "error": "Connection refused",
            "changes": ["connection_error"],
            "check_number": 1,
        }
        toon = w._to_toon(result)
        assert "ERROR" in toon
        assert "Connection refused" in toon

    def test_to_toon_with_ssl(self):
        w = HttpWatcher("web:example", "https://example.com")
        w._check_count = 2
        result = {
            "status_code": 200,
            "response_time_ms": 100,
            "changes": [],
            "check_number": 2,
            "ssl": {"days_until_expiry": 15, "expires": "Mar 15 2026"},
        }
        toon = w._to_toon(result)
        assert "SSL" in toon
        assert "15d" in toon


# =============================================================================
# ProcessWatcher tests
# =============================================================================

class TestProcessWatcher:
    def test_parse_target_process(self):
        t, v = ProcessWatcher._parse_target("proc:nginx")
        assert t == "process_name"
        assert v == "nginx"

    def test_parse_target_pid(self):
        t, v = ProcessWatcher._parse_target("pid:1234")
        assert t == "pid"
        assert v == "1234"

    def test_parse_target_port(self):
        t, v = ProcessWatcher._parse_target("port:8080")
        assert t == "port"
        assert v == "8080"

    def test_parse_target_tcp(self):
        t, v = ProcessWatcher._parse_target("tcp:localhost:5432")
        assert t == "tcp"
        assert v == "localhost:5432"

    def test_parse_target_service(self):
        t, v = ProcessWatcher._parse_target("service:postgresql")
        assert t == "service"
        assert v == "postgresql"

    def test_parse_target_bare(self):
        t, v = ProcessWatcher._parse_target("nginx")
        assert t == "process_name"
        assert v == "nginx"

    def test_init(self):
        w = ProcessWatcher("test:proc", "proc:nginx", poll_interval=5)
        assert w._target_type == "process_name"
        assert w._target_value == "nginx"
        assert w.poll_interval == 5.0

    def test_detect_changes_came_alive(self):
        w = ProcessWatcher("test:proc", "proc:nginx")
        w._prev_state = {"alive": False}
        result = {"alive": True}
        changes = w._detect_changes(result)
        assert "came_alive" in changes

    def test_detect_changes_went_down(self):
        w = ProcessWatcher("test:proc", "proc:nginx")
        w._prev_state = {"alive": True}
        result = {"alive": False}
        changes = w._detect_changes(result)
        assert "went_down" in changes

    def test_detect_changes_process_count(self):
        w = ProcessWatcher("test:proc", "proc:nginx")
        w._prev_state = {"alive": True, "process_count": 2}
        result = {"alive": True, "process_count": 4}
        changes = w._detect_changes(result)
        assert any("process_count:" in c for c in changes)

    def test_to_toon_up(self):
        w = ProcessWatcher("proc:nginx", "proc:nginx")
        w._check_count = 1
        result = {
            "alive": True,
            "changes": [],
            "check_number": 1,
            "processes": [{"pid": 100, "rss_kb": 4096, "cmdline": "nginx: master"}],
        }
        toon = w._to_toon(result)
        assert "UP" in toon
        assert "proc:nginx" in toon

    def test_to_toon_down(self):
        w = ProcessWatcher("proc:nginx", "proc:nginx")
        result = {
            "alive": False,
            "changes": ["went_down"],
            "check_number": 5,
        }
        toon = w._to_toon(result)
        assert "DOWN" in toon
        assert "went_down" in toon

    @pytest.mark.asyncio
    async def test_check_pid_current_process(self):
        """Check monitoring current process PID."""
        pid = os.getpid()
        w = ProcessWatcher("test:pid", f"pid:{pid}")
        result: dict = {"target_type": "pid", "target_value": str(pid)}
        await w._check_pid(result)
        assert result["alive"] is True

    @pytest.mark.asyncio
    async def test_check_pid_nonexistent(self):
        """Check monitoring non-existent PID."""
        w = ProcessWatcher("test:pid", "pid:999999999")
        result: dict = {"target_type": "pid", "target_value": "999999999"}
        await w._check_pid(result)
        assert result["alive"] is False


# =============================================================================
# DirectoryWatcher tests
# =============================================================================

class TestDirectoryWatcher:
    def test_init(self):
        w = DirectoryWatcher("test:dir", "dir:/tmp", poll_interval=3)
        assert w.path_or_url == "/tmp"
        assert w.poll_interval == 3.0
        assert w.recursive is True

    def test_init_without_prefix(self):
        w = DirectoryWatcher("test:dir", "/var/data")
        assert w.path_or_url == "/var/data"

    def test_human_size(self):
        assert DirectoryWatcher._human_size(0) == "0B"
        assert DirectoryWatcher._human_size(512) == "512B"
        assert "KB" in DirectoryWatcher._human_size(2048)
        assert "MB" in DirectoryWatcher._human_size(5 * 1024 * 1024)

    @pytest.mark.asyncio
    async def test_take_snapshot(self, tmp_path):
        (tmp_path / "file1.txt").write_text("hello")
        (tmp_path / "file2.py").write_text("x = 1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.txt").write_text("nested")

        w = DirectoryWatcher("test:dir", str(tmp_path))
        snapshot = await w._take_snapshot()
        assert len(snapshot) >= 4  # 2 files + 1 dir + 1 nested file
        assert any("file1.txt" in k for k in snapshot)
        assert any("file3.txt" in k for k in snapshot)

    @pytest.mark.asyncio
    async def test_initial_scan_emits_tree(self, tmp_path):
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.txt").write_text("doc")

        w = DirectoryWatcher("test:dir", str(tmp_path))
        await w._initial_scan()

        chunks = []
        while not w._queue.empty():
            chunks.append(await w._queue.get())

        assert len(chunks) == 1
        assert "dir-structure" in chunks[0].toon_spec
        assert chunks[0].is_delta is False

    @pytest.mark.asyncio
    async def test_detect_file_creation(self, tmp_path):
        (tmp_path / "original.txt").write_text("data")

        w = DirectoryWatcher("test:dir", str(tmp_path), poll_interval=0.5)
        await w._initial_scan()

        # Drain initial chunk
        while not w._queue.empty():
            await w._queue.get()

        # Create new file
        (tmp_path / "new_file.txt").write_text("new data")

        await w._check_changes()

        chunks = []
        while not w._queue.empty():
            chunks.append(await w._queue.get())

        assert len(chunks) == 1
        assert "dir-change" in chunks[0].toon_spec
        assert "CREATED" in chunks[0].toon_spec
        assert chunks[0].is_delta is True

    @pytest.mark.asyncio
    async def test_detect_file_deletion(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("temp")

        w = DirectoryWatcher("test:dir", str(tmp_path))
        await w._initial_scan()

        while not w._queue.empty():
            await w._queue.get()

        f.unlink()
        await w._check_changes()

        chunks = []
        while not w._queue.empty():
            chunks.append(await w._queue.get())

        assert len(chunks) == 1
        assert "DELETED" in chunks[0].toon_spec

    @pytest.mark.asyncio
    async def test_ignore_patterns(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("gitconfig")
        (tmp_path / "main.py").write_text("code")

        w = DirectoryWatcher("test:dir", str(tmp_path))
        snapshot = await w._take_snapshot()
        assert not any(".git" in k for k in snapshot)
        assert any("main.py" in k for k in snapshot)

    def test_build_tree_toon(self):
        w = DirectoryWatcher("test:dir", "/tmp")
        snapshot = {
            "src": {"type": "dir", "size": 0},
            f"src{os.sep}main.py": {"type": "file", "size": 1024},
            "README.md": {"type": "file", "size": 512},
        }
        toon = w._build_tree_toon(snapshot)
        assert "dir-structure" in toon
        assert "2 files" in toon
        assert "1 dirs" in toon


# =============================================================================
# DockerWatcher tests
# =============================================================================

class TestDockerWatcher:
    def test_init(self):
        w = DockerWatcher("test:docker", "docker:myapp")
        assert w.container_filter == "myapp"
        assert w.poll_interval == 15.0

    def test_init_all_containers(self):
        w = DockerWatcher("test:docker", "docker:*")
        assert w.container_filter == ""

    def test_detect_changes_new_container(self):
        w = DockerWatcher("test:docker", "docker:*")
        w._prev_containers = {"app1": {"state": "running"}}
        current = {
            "app1": {"state": "running"},
            "app2": {"state": "running"},
        }
        changes = w._detect_changes(current)
        assert any("new_container:app2" in c for c in changes)

    def test_detect_changes_removed_container(self):
        w = DockerWatcher("test:docker", "docker:*")
        w._prev_containers = {
            "app1": {"state": "running"},
            "app2": {"state": "running"},
        }
        current = {"app1": {"state": "running"}}
        changes = w._detect_changes(current)
        assert any("removed_container:app2" in c for c in changes)

    def test_detect_changes_state_change(self):
        w = DockerWatcher("test:docker", "docker:*")
        w._prev_containers = {"app1": {"state": "running"}}
        current = {"app1": {"state": "exited"}}
        changes = w._detect_changes(current)
        assert any("state_change" in c for c in changes)

    def test_to_toon(self):
        w = DockerWatcher("docker:all", "docker:*")
        result = {
            "check_number": 1,
            "container_count": 2,
            "running": 1,
            "stopped": 1,
            "changes": [],
            "containers": {
                "web": {"state": "running", "image": "nginx:latest", "status": "Up 2h"},
                "db": {"state": "exited", "image": "postgres:16", "status": "Exited (0)"},
            },
        }
        toon = w._to_toon(result)
        assert "docker" in toon
        assert "1 running" in toon
        assert "1 stopped" in toon
        assert "nginx" in toon


# =============================================================================
# DatabaseWatcher tests
# =============================================================================

class TestDatabaseWatcher:
    def test_init_sqlite(self):
        w = DatabaseWatcher("test:db", "db:test.db")
        assert w._dsn == "test.db"
        assert w._db_type == "sqlite"

    def test_init_sqlite_prefix(self):
        w = DatabaseWatcher("test:db", "sqlite:mydata.sqlite3")
        assert w._dsn == "mydata.sqlite3"
        assert w._db_type == "sqlite"

    def test_init_postgresql(self):
        w = DatabaseWatcher("test:db", "postgresql://localhost/mydb")
        assert w._db_type == "postgresql"

    def test_detect_db_type(self):
        w = DatabaseWatcher("t", "test.db")
        assert w._detect_db_type() == "sqlite"

    @pytest.mark.asyncio
    async def test_check_sqlite(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('Alice')")
        conn.execute("INSERT INTO users (name) VALUES ('Bob')")
        conn.commit()
        conn.close()

        w = DatabaseWatcher("test:db", f"db:{db_path}")
        result: dict = {"dsn": str(db_path), "db_type": "sqlite"}
        await w._check_sqlite(result)

        assert result["alive"] is True
        assert len(result["tables"]) == 1
        assert result["tables"][0]["name"] == "users"
        assert result["row_counts"]["users"] == 2
        assert result["schema_hash"] != ""

    @pytest.mark.asyncio
    async def test_check_sqlite_custom_queries(self, tmp_path):
        db_path = tmp_path / "test_q.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE events (id INTEGER, type TEXT, ts REAL)")
        conn.execute("INSERT INTO events VALUES (1, 'click', 1.0)")
        conn.execute("INSERT INTO events VALUES (2, 'view', 2.0)")
        conn.commit()
        conn.close()

        w = DatabaseWatcher("test:db", f"db:{db_path}",
                            queries=[{"name": "event_count", "sql": "SELECT COUNT(*) as cnt FROM events"}])
        result: dict = {"dsn": str(db_path), "db_type": "sqlite"}
        await w._check_sqlite(result)

        assert "query_results" in result
        assert "event_count" in result["query_results"]
        assert result["query_results"]["event_count"]["rows"] == 1

    @pytest.mark.asyncio
    async def test_check_sqlite_nonexistent(self, tmp_path):
        w = DatabaseWatcher("test:db", f"db:{tmp_path}/nonexistent.db")
        result: dict = {"dsn": f"{tmp_path}/nonexistent.db", "db_type": "sqlite"}
        await w._check_sqlite(result)
        assert result["alive"] is False

    def test_detect_changes_row_count(self):
        w = DatabaseWatcher("test:db", "db:test.db")
        w._prev_row_counts = {"users": 10}
        w._check_count = 2
        result = {"row_counts": {"users": 15}}
        changes = w._detect_changes(result)
        assert any("rows:users:+5" in c for c in changes)

    def test_detect_changes_schema(self):
        w = DatabaseWatcher("test:db", "db:test.db")
        w._prev_schema_hash = "abc123"
        result = {"schema_hash": "def456", "row_counts": {}}
        changes = w._detect_changes(result)
        assert "schema_changed" in changes

    def test_to_toon(self):
        w = DatabaseWatcher("db:main", "db:main.db")
        w._check_count = 1
        result = {
            "alive": True,
            "db_type": "sqlite",
            "changes": [],
            "check_number": 1,
            "tables": [{"name": "users", "type": "table"}],
            "row_counts": {"users": 100},
            "file_size": 1024 * 1024,
        }
        toon = w._to_toon(result)
        assert "db-check" in toon
        assert "UP" in toon
        assert "users" in toon
        assert "100 rows" in toon

    @pytest.mark.asyncio
    async def test_full_check_cycle(self, tmp_path):
        """Full check cycle: create DB, run check, add data, detect changes."""
        db_path = tmp_path / "cycle.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO items (val) VALUES ('a')")
        conn.commit()
        conn.close()

        w = DatabaseWatcher("test:db", f"db:{db_path}", poll_interval=0.5)
        await w._check()

        # Drain initial chunk
        chunks = []
        while not w._queue.empty():
            chunks.append(await w._queue.get())
        assert len(chunks) == 1
        assert "db-check" in chunks[0].toon_spec

        # Add more data
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO items (val) VALUES ('b')")
        conn.execute("INSERT INTO items (val) VALUES ('c')")
        conn.commit()
        conn.close()

        await w._check()
        chunks2 = []
        while not w._queue.empty():
            chunks2.append(await w._queue.get())
        assert len(chunks2) == 1
        assert "rows:items:+2" in chunks2[0].toon_spec


# =============================================================================
# NetworkWatcher tests
# =============================================================================

class TestNetworkWatcher:
    def test_init(self):
        w = NetworkWatcher("test:net", "net:8.8.8.8,1.1.1.1")
        assert w.targets == ["8.8.8.8", "1.1.1.1"]

    def test_init_with_ports(self):
        w = NetworkWatcher("test:net", "net:localhost", ports="80,443,8080")
        assert w.check_ports == [80, 443, 8080]

    def test_init_ping_prefix(self):
        w = NetworkWatcher("test:net", "ping:google.com")
        assert w.targets == ["google.com"]

    def test_init_dns_prefix(self):
        w = NetworkWatcher("test:net", "dns:example.com")
        assert w.targets == ["example.com"]

    def test_detect_changes_went_down(self):
        w = NetworkWatcher("test:net", "net:host1")
        w._prev_results = {"host1": {"reachable": True}}
        current = {"host1": {"reachable": False}}
        changes = w._detect_changes(current)
        assert any("went_down" in c for c in changes)

    def test_detect_changes_came_up(self):
        w = NetworkWatcher("test:net", "net:host1")
        w._prev_results = {"host1": {"reachable": False}}
        current = {"host1": {"reachable": True}}
        changes = w._detect_changes(current)
        assert any("came_up" in c for c in changes)

    def test_detect_changes_latency_spike(self):
        w = NetworkWatcher("test:net", "net:host1")
        w._prev_results = {"host1": {"reachable": True, "latency_ms": 10}}
        current = {"host1": {"reachable": True, "latency_ms": 50}}
        changes = w._detect_changes(current)
        assert any("latency_spike" in c for c in changes)

    def test_detect_changes_port_change(self):
        w = NetworkWatcher("test:net", "net:host1")
        w._prev_results = {"host1": {"reachable": True, "ports": {80: {"open": True}}}}
        current = {"host1": {"reachable": True, "ports": {80: {"open": False}}}}
        changes = w._detect_changes(current)
        assert any("port_closed" in c for c in changes)

    def test_detect_changes_dns_change(self):
        w = NetworkWatcher("test:net", "net:host1")
        w._prev_results = {"host1": {"reachable": True, "resolved_ips": ["1.2.3.4"]}}
        current = {"host1": {"reachable": True, "resolved_ips": ["5.6.7.8"]}}
        changes = w._detect_changes(current)
        assert any("dns_changed" in c for c in changes)

    def test_to_toon(self):
        w = NetworkWatcher("net:check", "net:8.8.8.8")
        summary = {
            "check_number": 1,
            "targets": 1,
            "reachable": 1,
            "unreachable": 0,
            "changes": [],
            "results": {
                "8.8.8.8": {
                    "reachable": True,
                    "latency_ms": 15.2,
                    "dns": {"ips": ["8.8.8.8"]},
                },
            },
        }
        toon = w._to_toon(summary)
        assert "network-check" in toon
        assert "1/1 reachable" in toon
        assert "UP" in toon

    @pytest.mark.asyncio
    async def test_resolve_dns_localhost(self):
        w = NetworkWatcher("test:net", "net:localhost")
        result = await w._resolve_dns("localhost")
        assert result["success"] is True
        assert len(result["ips"]) >= 1
