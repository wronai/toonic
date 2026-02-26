# Plugin System (Watchers)

## Przegląd

Każdy typ źródła danych jest obsługiwany przez osobny plugin (Watcher).
System pluginów używa wzorca Registry — analogicznie do `FormatRegistry` w toonic core.

## Istniejące pluginy

| Plugin | Kategoria | Obsługuje |
|--------|-----------|-----------|
| `FileWatcher` | code/config/data | Katalogi, pliki (polling + TOON) |
| `LogWatcher` | logs | Pliki logów (tail -f + kategoryzacja) |
| `StreamWatcher` | video/audio | RTSP, pliki video (OpenCV + scene detection) |

## Tworzenie nowego pluginu

1. Stwórz plik `toonic/server/watchers/my_watcher.py`
2. Dziedzicz po `BaseWatcher`
3. Zaimplementuj `start()`, `stop()`, `supports()`
4. Zarejestruj w `WatcherRegistry`

```python
from toonic.server.watchers.base import BaseWatcher, WatcherRegistry
from toonic.server.models import ContextChunk, SourceCategory

class MQTTWatcher(BaseWatcher):
    category = SourceCategory.DATA

    async def start(self):
        await super().start()
        # Connect to MQTT broker, subscribe to topics
        self._task = asyncio.create_task(self._listen())

    async def _listen(self):
        while self.running:
            message = await self._receive()
            await self.emit(ContextChunk(
                source_id=f"mqtt:{message.topic}",
                category=SourceCategory.DATA,
                toon_spec=self._to_toon(message),
                is_delta=True,
            ))

    @classmethod
    def supports(cls, path_or_url: str) -> float:
        return 0.9 if path_or_url.startswith("mqtt://") else 0.0

WatcherRegistry.register(MQTTWatcher)
```

## API BaseWatcher

| Metoda | Opis |
|--------|------|
| `start()` | Rozpocznij obserwację |
| `stop()` | Zatrzymaj i posprzątaj |
| `emit(chunk)` | Wyślij ContextChunk do kolejki |
| `get_chunks()` | AsyncIterator[ContextChunk] |
| `supports(path)` | 0.0-1.0 confidence |

## WatcherRegistry

```python
# Rozpoznanie najlepszego pluginu
cls = WatcherRegistry.resolve("rtsp://cam1")  # → StreamWatcher

# Utworzenie instancji
watcher = WatcherRegistry.create("cam1", "video", "rtsp://cam1:554/stream")

# Lista pluginów
WatcherRegistry.list_all()  # → ["FileWatcher", "LogWatcher", "StreamWatcher"]
```
