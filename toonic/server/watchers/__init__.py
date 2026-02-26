"""Source watchers — plugins for different data sources."""

from toonic.server.watchers.base import BaseWatcher, WatcherRegistry
from toonic.server.watchers.file_watcher import FileWatcher
from toonic.server.watchers.log_watcher import LogWatcher
from toonic.server.watchers.stream_watcher import StreamWatcher
from toonic.server.watchers.http_watcher import HttpWatcher
from toonic.server.watchers.process_watcher import ProcessWatcher
from toonic.server.watchers.directory_watcher import DirectoryWatcher
from toonic.server.watchers.docker_watcher import DockerWatcher
from toonic.server.watchers.database_watcher import DatabaseWatcher
from toonic.server.watchers.network_watcher import NetworkWatcher

__all__ = [
    "BaseWatcher", "WatcherRegistry",
    "FileWatcher", "LogWatcher", "StreamWatcher",
    "HttpWatcher", "ProcessWatcher", "DirectoryWatcher",
    "DockerWatcher", "DatabaseWatcher", "NetworkWatcher",
]
