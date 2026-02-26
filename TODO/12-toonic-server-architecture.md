---
title: "Toonic Server — Architektura Dwukierunkowego Strumieniowania TOON"
slug: toonic-server-architecture
date: 2026-02-26
author: WronAI
categories: [projekty, toonic, architektura, server]
tags: [toonic, TOON, server, streaming, gRPC, RTSP, LLM, multimodal, MCP]
excerpt: "Propozycja architektury serwera Toonic do dwukierunkowego strumieniowania danych między źródłami (dysk, protokoły RTSP, logi) a modelami LLM — z formatem TOON jako warstwą kompresji kontekstu."
---

# Toonic Server — Architektura Dwukierunkowego Strumieniowania TOON

## 1. Problem i cel

Potrzebujemy serwera, który:

1. **Zbiera dane z wielu źródeł jednocześnie** — pliki na dysku (kod, config, dane, logi), strumienie RTSP (video/audio z kamer), protokoły sieciowe
2. **Konwertuje je na format TOON** w czasie rzeczywistym — kompresja 5-400x
3. **Strumieniuje kontekst do LLM** inkrementalnie — najpierw kod, potem zmiany, potem logi, potem strumienie
4. **Odbiera odpowiedzi LLM** i wykonuje akcje — fix kodu, raport z analizy, alert
5. **Obsługuje wiele modeli** — text model dla kodu, multimodal dla video/audio, różni providerzy

## 2. Rekomendacja technologiczna: gRPC + Streamable HTTP

### Dlaczego gRPC (a nie REST, WebSocket, MCP stdio)?

| Cecha | REST | WebSocket | MCP stdio | MCP Streamable HTTP | **gRPC** |
|-------|------|-----------|-----------|---------------------|----------|
| Bidirectional streaming | ✗ | ✓ | ✓ (local) | ✓ | **✓** |
| Binary frames (video/audio) | ✗ | ✓ | ✗ | ✗ | **✓ (protobuf)** |
| Backpressure | ✗ | ✗ | ✗ | ✗ | **✓ (HTTP/2 flow)** |
| Multi-language | ✓ | ✓ | ✗ | ✓ | **✓ (codegen)** |
| Latency | ~50ms | ~5ms | ~1ms | ~10ms | **~2ms** |
| Typ-bezpieczeństwo | ✗ | ✗ | JSON Schema | JSON Schema | **✓ (protobuf)** |

**gRPC bidi streaming** to najlepsze rozwiązanie dla tego use-case'u:
- HTTP/2 multiplexing — wiele strumieni na jednym połączeniu
- Protobuf — natywna serializacja binary (base64 audio/video bez overhead)
- Flow control — backpressure gdy LLM nie nadąża
- Codegen — ten sam `.proto` generuje klienta i serwer w Python i Rust

### Warstwa MCP (opcjonalna)

gRPC jest transportem wewnętrznym serwera. Na zewnątrz serwer eksponuje:
- **MCP Streamable HTTP** — dla integracji z Claude Desktop, Windsurf, itp.
- **gRPC** — dla programistycznego dostępu i Rust klienta
- **REST/JSON** — prosty fallback do debugowania

## 3. Architektura wysokopoziomowa

```
┌────────────────────────────────────────────────────────────┐
│                      TOONIC SERVER                         │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │
│  │ Source   │  │ Source   │  │ Source   │  │ Source    │   │
│  │ Watcher  │  │ Watcher  │  │ Watcher  │  │ Watcher   │   │
│  │ (code)   │  │ (config) │  │ (logs)   │  │ (rtsp)    │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬──────┘   │
│       │             │             │             │          │
│       ▼             ▼             ▼             ▼          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              TOON Conversion Pipeline                │  │
│  │  FileHandler.parse() → FileLogic → to_spec('toon')   │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                  │
│                         ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Context Accumulator                      │   │
│  │  Ring buffer: [code_spec, config_spec, log_tail,     │   │
│  │                video_keyframes, audio_speech]          │   │
│  │  Priority queue → token budget allocation             │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LLM Router                               │   │
│  │  text → gemini-flash | code → claude | video → gpt4o │   │
│  │  via litellm/openrouter                               │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Action Executor                          │   │
│  │  fix_code() | generate_report() | send_alert()        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ── External APIs ──────────────────────────────────────    │
│  gRPC bidi stream  │  MCP Streamable HTTP  │  REST/JSON    │
└─────────────────────────────────────────────────────────────┘
```

## 4. Protobuf Schema — rdzeń komunikacji

```protobuf
syntax = "proto3";
package toonic;

// ═══════════════════════════════════════════════
// Typy danych
// ═══════════════════════════════════════════════

enum SourceCategory {
  CODE = 0;
  CONFIG = 1;
  DATA = 2;
  LOGS = 3;
  VIDEO = 4;
  AUDIO = 5;
  DOCUMENT = 6;
  DATABASE = 7;
  API = 8;
  INFRA = 9;
}

enum ContentEncoding {
  TEXT_UTF8 = 0;
  BASE64_JPEG = 1;
  BASE64_ULAW = 2;
  BASE64_PCM16 = 3;
  TOON = 4;
}

// Jeden chunk kontekstu (inkrementalny)
message ContextChunk {
  string source_id = 1;           // "file:src/main.py" | "rtsp://cam1" | "log:app.log"
  SourceCategory category = 2;
  ContentEncoding encoding = 3;
  string toon_spec = 4;           // TOON-compressed representation
  bytes raw_data = 5;             // binary data (base64 keyframes, audio segments)
  double timestamp = 6;
  bool is_delta = 7;              // true = incremental change, false = full snapshot
  map<string, string> metadata = 8;
}

// Cel analizy
message Goal {
  string description = 1;         // "fix bugs in auth module"
  string type = 2;                // "fix" | "analyze" | "optimize" | "monitor"
  repeated string focus_paths = 3; // ["src/auth/", "tests/"]
  map<string, string> model_routing = 4; // {"text": "google/gemini-flash", "video": "openai/gpt-4o"}
  int32 max_tokens_per_request = 5;
  double interval_seconds = 6;    // 0 = one-shot, >0 = continuous loop
}

// Odpowiedź LLM → akcja
message ActionResponse {
  string action_type = 1;         // "code_fix" | "report" | "alert" | "none"
  string content = 2;             // wygenerowany kod / raport / alert
  string target_path = 3;         // plik do modyfikacji
  double confidence = 4;
  repeated string affected_files = 5;
  map<string, string> metadata = 6;
}

// Status serwera
message ServerStatus {
  int32 active_watchers = 1;
  int32 total_chunks_sent = 2;
  int64 total_tokens_used = 3;
  double uptime_seconds = 4;
  map<string, string> watcher_status = 5;  // source_id → "running" | "paused" | "error"
}

// ═══════════════════════════════════════════════
// Serwis gRPC — dwukierunkowy streaming
// ═══════════════════════════════════════════════

service TonicService {
  // Główny strumień: klient wysyła goal + config, serwer strumieniuje kontekst + akcje
  rpc StreamAnalysis(stream ClientMessage) returns (stream ServerMessage);

  // Jednorazowa konwersja pliku → TOON
  rpc ConvertToToon(ConvertRequest) returns (ConvertResponse);

  // Status serwera
  rpc GetStatus(StatusRequest) returns (ServerStatus);
}

message ClientMessage {
  oneof payload {
    Goal goal = 1;                 // ustaw cel
    SourceConfig add_source = 2;   // dodaj źródło danych
    string remove_source = 3;      // usuń źródło (source_id)
    string command = 4;            // "pause" | "resume" | "stop"
    ActionFeedback feedback = 5;   // feedback na akcję LLM
  }
}

message ServerMessage {
  oneof payload {
    ContextChunk context = 1;      // nowy chunk kontekstu
    ActionResponse action = 2;     // rekomendacja akcji od LLM
    ServerStatus status = 3;       // status update
    string error = 4;              // error message
    string log = 5;                // debug log
  }
}

message SourceConfig {
  string source_id = 1;
  SourceCategory category = 2;
  string path_or_url = 3;         // "/project/src/" | "rtsp://192.168.1.100:554/stream"
  bool watch_changes = 4;         // true = inotify/polling
  double poll_interval_s = 5;     // for streams: how often to sample
  map<string, string> options = 6; // {"vad_aggressiveness": "2", "scene_threshold": "0.4"}
}

message ActionFeedback {
  string action_id = 1;
  bool accepted = 2;
  string reason = 3;
}

message ConvertRequest {
  string file_path = 1;
  string format = 2;              // "toon" | "yaml" | "json"
}

message ConvertResponse {
  string spec = 1;
  int32 token_count = 2;
  string category = 3;
}

message StatusRequest {}
```

## 5. Kluczowe komponenty wewnętrzne

### 5.1 Source Watchers (pluginy wejściowe)

Każdy watcher to niezależny async task/thread:

| Watcher | Trigger | Output | Biblioteka |
|---------|---------|--------|-----------|
| **FileWatcher** | inotify/poll | ContextChunk (is_delta=true) | watchfiles (Py), notify (Rust) |
| **LogTailer** | tail -f | ContextChunk z last N lines | tailer (Py), linemux (Rust) |
| **RTSPWatcher** | frame buffer | keyframe ContextChunks | OpenCV (Py), gstreamer-rs (Rust) |
| **AudioWatcher** | VAD trigger | speech segment chunks | webrtcvad+numpy (Py), webrtc-vad (Rust) |
| **GitWatcher** | git diff | delta spec | gitpython (Py), git2 (Rust) |

### 5.2 Context Accumulator (budżet tokenów)

LLM ma ograniczone okno kontekstowe. Accumulator zarządza priorytetami:

```
Token budget: 100k
├── code_spec (TOON):     40k tokens (priority: HIGH, refresh: on-change)
├── config_spec:           5k tokens (priority: MEDIUM, refresh: on-change)
├── log_tail (last 100):  10k tokens (priority: HIGH, refresh: 5s)
├── video_keyframes:      20k tokens (priority: LOW, refresh: 10s)
├── audio_speech:         15k tokens (priority: MEDIUM, refresh: on-speech)
└── goal + system prompt: 10k tokens (priority: FIXED)
```

Strategia eviction: LRU z priorytetami. Video/audio keyframes rotują najszybciej.

### 5.3 LLM Router (model per modality)

```yaml
# toonic-server.yaml
models:
  text:
    provider: openrouter
    model: google/gemini-2.5-flash-preview
    max_tokens: 8192
  code:
    provider: openrouter
    model: anthropic/claude-sonnet-4
    max_tokens: 16384
  multimodal:   # video frames + audio
    provider: openrouter
    model: google/gemini-2.5-flash-preview
    max_tokens: 8192
    supports: [text, image, audio]
  fallback:
    provider: ollama
    model: qwen3:8b
    max_tokens: 4096
```

Router decyduje na podstawie `SourceCategory`:
- CODE, CONFIG, DATA, DATABASE → `code` model
- LOGS → `text` model
- VIDEO, AUDIO → `multimodal` model (z base64 frames)
- mix → `multimodal` jeśli dostępny, inaczej `text` z TOON-only (bez raw data)

## 6. Biblioteki — Python

### Core
| Komponent | Biblioteka | Dlaczego |
|-----------|-----------|---------|
| **gRPC server** | `grpcio` + `grpcio-tools` | oficjalny Python gRPC, bidi streaming |
| **Async runtime** | `asyncio` + `anyio` | native Python async, kompatybilność z grpcio.aio |
| **Protobuf** | `grpcio-tools` (protoc) | generuje Python stub z .proto |
| **Config** | `pydantic-settings` | type-safe config z env/yaml |

### Source Watchers
| Komponent | Biblioteka | Dlaczego |
|-----------|-----------|---------|
| **File watching** | `watchfiles` (Rust-backed) | 10x szybszy niż watchdog, zero CPU idle |
| **Log tailing** | `tailer` lub `pygtail` | tail -f z offset tracking |
| **RTSP video** | `opencv-python` (cv2) | Pure OpenCV capture, bez FFmpeg |
| **Audio VAD** | `webrtcvad` + `numpy` | <0.1ms latency, 20ms frames |
| **Git changes** | `gitpython` | diff tracking |

### LLM Integration
| Komponent | Biblioteka | Dlaczego |
|-----------|-----------|---------|
| **LLM routing** | `litellm` | unified API: OpenRouter, Ollama, OpenAI, Anthropic |
| **Multimodal** | `litellm` (base64 images) | obsługuje vision models z base64 |
| **Rate limiting** | `aiolimiter` | token bucket per provider |

### Opcjonalne
| Komponent | Biblioteka | Dlaczego |
|-----------|-----------|---------|
| **MCP server** | `mcp` (oficjalny SDK) | Streamable HTTP transport dla IDE |
| **REST fallback** | `fastapi` + `uvicorn` | debug API, web dashboard |
| **Metrics** | `prometheus-client` | monitoring tokens/latency |

## 7. Biblioteki — Rust

### Core
| Komponent | Biblioteka (crate) | Dlaczego |
|-----------|-----------|---------|
| **gRPC server** | `tonic` + `prost` | najlepszy Rust gRPC, native async |
| **Async runtime** | `tokio` | de facto standard async Rust |
| **Protobuf** | `tonic-build` + `prost-build` | codegen z .proto |
| **Config** | `config` + `serde` | type-safe config |
| **CLI** | `clap` | argument parsing |

### Source Watchers
| Komponent | Biblioteka (crate) | Dlaczego |
|-----------|-----------|---------|
| **File watching** | `notify` (v7) | cross-platform inotify/kqueue/FSEvents |
| **Log tailing** | `linemux` | async multi-file tail |
| **RTSP video** | `gstreamer-rs` + `gstreamer-app` | Pure GStreamer (nie FFmpeg), RTSP native |
| **Alternatywa video** | `retina` | pure Rust RTSP client, zero C deps |
| **Audio VAD** | `webrtc-vad` | Rust binding do WebRTC VAD |
| **Audio processing** | `dasp` | DSP: resampling, filtering (zamiast numpy) |
| **Git changes** | `git2` | libgit2 binding |
| **Image encoding** | `image` + `turbojpeg` | JPEG encode/decode |

### LLM Integration
| Komponent | Biblioteka (crate) | Dlaczego |
|-----------|-----------|---------|
| **HTTP client** | `reqwest` | async HTTP dla OpenRouter/Ollama API |
| **JSON** | `serde_json` | serializacja request/response |
| **Base64** | `base64` | encoding multimodal data |
| **SSE client** | `eventsource-client` | streaming responses od LLM |

### Opcjonalne
| Komponent | Biblioteka (crate) | Dlaczego |
|-----------|-----------|---------|
| **REST API** | `axum` | lightweight web framework |
| **Metrics** | `metrics` + `metrics-exporter-prometheus` | Prometheus export |
| **Tracing** | `tracing` + `tracing-subscriber` | structured logging |

## 8. Struktura projektu — Python

```
toonic-server-py/
├── pyproject.toml
├── proto/
│   └── toonic.proto                    # shared protobuf schema
├── toonic_server/
│   ├── __init__.py
│   ├── __main__.py                     # python -m toonic_server
│   ├── config.py                       # ServerConfig (pydantic)
│   ├── server.py                       # gRPC server + bidi streaming main loop
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── accumulator.py              # Context Accumulator (token budget, priority queue)
│   │   ├── router.py                   # LLM Router (model per modality)
│   │   ├── executor.py                 # Action Executor (apply fixes, generate reports)
│   │   └── scheduler.py               # Watcher lifecycle manager
│   │
│   ├── watchers/                       # Source Watcher plugins
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseWatcher Protocol
│   │   ├── file_watcher.py             # FileWatcher (watchfiles + toonic handlers)
│   │   ├── log_watcher.py              # LogTailer (tail -f + TOON compression)
│   │   ├── git_watcher.py              # GitWatcher (diff → delta TOON)
│   │   ├── rtsp_watcher.py             # RTSPWatcher (OpenCV + SceneDetector)
│   │   ├── audio_watcher.py            # AudioWatcher (VAD + μ-law)
│   │   └── protocol_watcher.py         # Generic protocol watcher (HTTP, MQTT, etc.)
│   │
│   ├── llm/                            # LLM integration
│   │   ├── __init__.py
│   │   ├── client.py                   # LiteLLM wrapper z retry/fallback
│   │   ├── multimodal.py               # Base64 encoding for vision models
│   │   └── prompts.py                  # Goal-specific prompt templates
│   │
│   ├── transport/                      # External APIs
│   │   ├── __init__.py
│   │   ├── grpc_service.py             # gRPC TonicService implementation
│   │   ├── mcp_service.py              # MCP Streamable HTTP bridge
│   │   └── rest_api.py                 # FastAPI debug/dashboard
│   │
│   └── generated/                      # auto-generated from proto
│       ├── toonic_pb2.py
│       └── toonic_pb2_grpc.py
│
├── tests/
│   ├── test_accumulator.py
│   ├── test_watchers.py
│   ├── test_router.py
│   └── test_integration.py
│
├── examples/
│   ├── 01_analyze_project.py           # toonic-server analyze ./myproject --goal "fix bugs"
│   ├── 02_monitor_rtsp.py              # toonic-server watch rtsp://cam1 --goal "detect anomalies"
│   └── 03_multi_source.py              # code + logs + camera combined
│
└── toonic-server.yaml                  # default config
```

## 9. Struktura projektu — Rust

```
toonic-server-rs/
├── Cargo.toml
├── build.rs                            # tonic-build protobuf codegen
├── proto/
│   └── toonic.proto                    # shared (symlink to Python version)
│
├── src/
│   ├── main.rs                         # CLI + server startup
│   ├── config.rs                       # ServerConfig (serde)
│   ├── server.rs                       # gRPC server + bidi streaming
│   │
│   ├── core/
│   │   ├── mod.rs
│   │   ├── accumulator.rs              # Context Accumulator
│   │   ├── router.rs                   # LLM Router
│   │   ├── executor.rs                 # Action Executor
│   │   └── scheduler.rs               # Watcher lifecycle
│   │
│   ├── watchers/
│   │   ├── mod.rs
│   │   ├── traits.rs                   # Watcher trait
│   │   ├── file_watcher.rs             # notify crate
│   │   ├── log_watcher.rs              # linemux
│   │   ├── git_watcher.rs              # git2
│   │   ├── rtsp_watcher.rs             # retina / gstreamer-rs
│   │   └── audio_watcher.rs            # webrtc-vad + dasp
│   │
│   ├── toon/
│   │   ├── mod.rs
│   │   ├── parser.rs                   # TOON parser (port from Python)
│   │   ├── generator.rs                # TOON generator
│   │   └── handlers/                   # File type handlers (port)
│   │       ├── mod.rs
│   │       ├── code.rs
│   │       ├── document.rs
│   │       ├── data.rs
│   │       ├── config.rs
│   │       └── sql.rs
│   │
│   ├── llm/
│   │   ├── mod.rs
│   │   ├── client.rs                   # reqwest-based LLM client
│   │   ├── multimodal.rs               # base64 image/audio encoding
│   │   └── prompts.rs                  # prompt templates
│   │
│   └── generated/                      # auto-generated by tonic-build
│       └── toonic.rs
│
├── tests/
│   ├── accumulator_test.rs
│   ├── watcher_test.rs
│   └── integration_test.rs
│
└── examples/
    ├── analyze_project.rs
    └── monitor_rtsp.rs
```

## 10. System pluginów

### Zasada: jeden plugin = jeden typ źródła danych

```python
# Python — BaseWatcher Protocol
class Watcher(Protocol):
    """Plugin interface for data sources."""
    
    source_id: str
    category: SourceCategory
    
    async def start(self) -> None:
        """Start watching/capturing."""
        ...
    
    async def stop(self) -> None:
        """Stop and cleanup."""
        ...
    
    async def get_chunks(self) -> AsyncIterator[ContextChunk]:
        """Yield context chunks as they arrive."""
        ...
    
    def supports(self, path_or_url: str) -> float:
        """0.0-1.0 confidence that this watcher handles this source."""
        ...
```

```rust
// Rust — Watcher trait
#[async_trait]
pub trait Watcher: Send + Sync {
    fn source_id(&self) -> &str;
    fn category(&self) -> SourceCategory;
    
    async fn start(&mut self) -> Result<()>;
    async fn stop(&mut self) -> Result<()>;
    
    /// Returns a stream of context chunks
    fn chunks(&self) -> Pin<Box<dyn Stream<Item = ContextChunk> + Send>>;
    
    /// 0.0-1.0 confidence
    fn supports(&self, path_or_url: &str) -> f32;
}
```

### Rejestracja pluginów

```python
# Python
class WatcherRegistry:
    _watchers: List[Type[Watcher]] = []
    
    @classmethod
    def register(cls, watcher_cls: Type[Watcher]) -> None:
        cls._watchers.append(watcher_cls)
    
    @classmethod
    def resolve(cls, source: str) -> Optional[Watcher]:
        """Find best watcher for source (like FormatRegistry.resolve)."""
        scores = [(w.supports(source), w) for w in cls._watchers]
        best_score, best_cls = max(scores, key=lambda x: x[0])
        return best_cls() if best_score > 0.0 else None
```

### Dodawanie nowego pluginu

1. Stwórz plik `watchers/mqtt_watcher.py`
2. Zaimplementuj `Watcher` Protocol
3. Zarejestruj w `watchers/__init__.py`

Przykład:
```python
class MQTTWatcher:
    """Plugin for MQTT protocol streams."""
    category = SourceCategory.DATA
    requires = ('paho-mqtt',)
    
    def supports(self, path_or_url: str) -> float:
        return 0.9 if path_or_url.startswith('mqtt://') else 0.0
    
    async def get_chunks(self) -> AsyncIterator[ContextChunk]:
        async for message in self.mqtt_client.messages():
            yield ContextChunk(
                source_id=f"mqtt:{message.topic}",
                category=SourceCategory.DATA,
                toon_spec=self._to_toon(message),
                timestamp=time.time(),
                is_delta=True,
            )
```

## 11. Flow — przykład użycia

```bash
# Start serwera
toonic-server start \
  --source "file:./src/" \
  --source "file:./config/" \
  --source "log:./logs/app.log" \
  --source "rtsp://192.168.1.100:554/stream" \
  --goal "find and fix bugs in authentication module" \
  --model-text "google/gemini-2.5-flash-preview" \
  --model-code "anthropic/claude-sonnet-4" \
  --model-multimodal "google/gemini-2.5-flash-preview" \
  --interval 30
```

Sekwencja:

1. **T=0s** — Server startuje, rejestruje watchers
2. **T=0.1s** — FileWatcher skanuje `./src/`, generuje pełny TOON spec kodu (~40k tokenów)
3. **T=0.2s** — FileWatcher skanuje `./config/`, TOON spec (~5k tokenów)
4. **T=0.3s** — LogTailer zaczyna tail `app.log`, ostatnie 100 linii → TOON
5. **T=0.5s** — RTSPWatcher łączy się z kamerą, buforuje klatki
6. **T=1.0s** — **Pierwszy request do LLM**: code_spec + config_spec + log_tail + goal
7. **T=3.0s** — LLM odpowiada: "Found potential null check issue in auth.py:42"
8. **T=3.1s** — ActionResponse: code_fix suggested
9. **T=30s** — **Loop**: LogTailer wykrył nowy ERROR → delta chunk → LLM query z nowym kontekstem
10. **T=35s** — FileWatcher wykrył zmianę w `auth.py` → delta TOON → LLM "verify fix"

## 12. Obsługiwane protokoły i formaty

### Protokoły strumieniowe
| Protokół | Watcher | Biblioteka Py | Biblioteka Rust |
|----------|---------|--------------|----------------|
| **RTSP** (video) | RTSPWatcher | opencv-python | retina / gstreamer-rs |
| **RTSP** (audio) | AudioWatcher | webrtcvad+numpy | webrtc-vad+dasp |
| **HTTP/SSE** | HTTPWatcher | httpx + httpx-sse | reqwest + eventsource |
| **WebSocket** | WSWatcher | websockets | tokio-tungstenite |
| **MQTT** | MQTTWatcher | paho-mqtt | rumqttc |
| **gRPC** (external) | GRPCWatcher | grpcio | tonic |
| **TCP raw** | TCPWatcher | asyncio.streams | tokio::net |
| **UDP** | UDPWatcher | asyncio.DatagramProtocol | tokio::net::UdpSocket |
| **Serial/RS-232** | SerialWatcher | pyserial-asyncio | tokio-serial |

### Formaty plików (via toonic handlers)
| Format | Handler | Kategoria |
|--------|---------|----------|
| `.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, `.cs` | CodeHandler | code |
| `.md`, `.rst`, `.txt` | DocumentHandler | document |
| `.csv`, `.tsv`, `.json` | DataHandler | data |
| `.env`, `Dockerfile`, `docker-compose.yml` | ConfigHandler | config |
| `.sql` | SqlHandler | database |
| `.yaml` (OpenAPI) | ApiHandler | api |
| `.yaml` (K8s, GH Actions) | InfraHandler | infra |
| `.mp4`, `.avi`, `.mkv` | VideoHandler | video |
| `.wav`, `.mp3`, `.flac` | AudioHandler | audio |
| `.log`, `.jsonl` | LogHandler | logs |

## 13. Rekomendacja kolejności implementacji

### Faza 1 — MVP (Python, ~2 tyg)
1. gRPC server z bidi streaming (grpcio.aio)
2. FileWatcher (watchfiles + istniejące toonic handlers)
3. LogTailer
4. Context Accumulator (prosty ring buffer)
5. LLM Client (litellm)
6. CLI: `toonic-server start --source file:./src/ --goal "analyze"`

### Faza 2 — Multimodal (Python, ~2 tyg)
1. RTSPWatcher (OpenCV, reuse LowQRTSPExtractor)
2. AudioWatcher (VAD, reuse SpeechDetector + MuLawCodec)
3. Multimodal LLM routing (base64 images → vision model)
4. Evidence Graph integration

### Faza 3 — Production (Python + Rust start, ~3 tyg)
1. MCP Streamable HTTP transport
2. REST debug API (FastAPI)
3. Token budget optimization
4. Rust port: core + gRPC + FileWatcher + LogTailer

### Faza 4 — Full Rust (Rust, ~4 tyg)
1. TOON parser/generator port
2. RTSP watcher (retina)
3. Audio watcher (webrtc-vad + dasp)
4. LLM client (reqwest + SSE)
5. Plugin system (trait-based)

## 14. Kluczowe decyzje architektoniczne

1. **gRPC jako transport wewnętrzny** — nie MCP stdio (zbyt wolny dla binarnych danych), nie REST (brak streaming). MCP Streamable HTTP jako bridge dla IDE.

2. **TOON jako warstwa kompresji** — wszystkie źródła danych przechodzą przez istniejące toonic handlers. Video/audio dodatkowo mają raw base64 dla multimodal models.

3. **Inkrementalne delty** — po pierwszym full snapshot, watchers wysyłają tylko zmiany (is_delta=true). Redukcja bandwidth 10-100x.

4. **Token budget management** — Accumulator zarządza oknem kontekstowym LLM. Priorytet: goal-related code > logs > config > video > audio.

5. **Model routing** — różne modele do różnych typów danych. Nie jeden model-do-wszystkiego, ale specjalizacja: code model widzi TOON, vision model widzi keyframes.

6. **Shared proto** — jeden `toonic.proto` generuje klienty w Python i Rust. Interoperability od dnia 0.

---

*Architektura Toonic Server v1.0 — dwukierunkowe strumieniowanie TOON dla LLM. gRPC + MCP, Python + Rust, pluginy per źródło danych.*
