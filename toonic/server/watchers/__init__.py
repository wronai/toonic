"""Source watchers — plugins for different data sources."""

from toonic.server.watchers.base import BaseWatcher, WatcherRegistry
from toonic.server.watchers.file_watcher import FileWatcher
from toonic.server.watchers.log_watcher import LogWatcher
from toonic.server.watchers.stream_watcher import StreamWatcher

__all__ = ["BaseWatcher", "WatcherRegistry", "FileWatcher", "LogWatcher", "StreamWatcher"]
