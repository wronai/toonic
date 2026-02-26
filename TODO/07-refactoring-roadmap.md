---
title: "Roadmapa Refaktoryzacji v4.2 — Od Code2Logic do Toonic Evidence Graph"
slug: refactoring-roadmap-v4
date: 2026-02-26
author: WronAI
categories: [projekty, toonic, architektura]
tags: [refaktoryzacja, architektura, FileHandler, FormatRegistry, pipeline, multimodal, evidence-graph, video, audio, VAD, RTSP]
excerpt: "Kompletny plan transformacji code2logic w Toonic v4.2 — 8 etapów od fundamentu architektonicznego przez handlery dokumentów, danych, API i infrastruktury, aż do multimodalnego Evidence Graph z PureCV video, VAD audio i fuzji multi-cam. Łącznie ~6800 linii nowego kodu w architekturze addytywnej."
featured_image: toonic-refactoring-v4-stages.png
---

# Roadmapa Refaktoryzacji v4.2 — Od Code2Logic do Toonic Evidence Graph

## Kontekst i ewolucja wizji

Code2Logic zaczynał jako kompresor kodu źródłowego — AST do YAML/TOON. Toonic rozszerza tę filozofię na wszystko co ma strukturę: dokumenty, konfiguracje, schematy SQL, API, infrastrukturę. Evidence Graph v4.2 to kulminacja tej ewolucji — multimodalny pipeline, w którym kod, dokumenty, video z kamer RTSP i audio z detekcją mowy trafiają do jednego grafu dowodowego dla LLM.

Zasada przewodnia: LLM nie czyta surowych gigabajtów. Dostaje lekki indeks (1-5 kB), a gdy potrzebuje dowodu — dociąga konkretny fragment w niskiej jakości wystarczającej do rozumowania.

Projekt bazowy to 156 modułów i 42 706 linii kodu. Refaktoryzacja nie jest rewolucją — to systematyczne wypełnianie istniejącej struktury katalogów (`core/`, `formats/`) nowymi handlerami, przy zachowaniu kompatybilności wstecznej.

## Kluczowe problemy rozwiązane w zrewidowanej architekturze

Analiza krytyczna planów v1.0–v3.0 ujawniła trzy fundamentalne problemy. Po pierwsze, plany tworzyły nowe pliki (`base_logic.py`, `registry.py`) zamiast wypełniać istniejące stuby (`core/__init__.py`, `formats/__init__.py`). Po drugie, rozszerzenie pliku było jedynym sposobem identyfikacji typu — co jest błędne, gdy `.yaml` może być OpenAPI, Kubernetes, GitHub Actions lub Ansible. Po trzecie, auto-rejestracja pluginów przy imporcie prowadziła do circular dependencies.

Zrewidowana architektura wprowadza: `FileHandler Protocol` (jeden obiekt = jeden typ pliku, trzy metody zamiast trzech klas), `FormatRegistry` z dwuetapowym rozwiązywaniem (rozszerzenie → kandydaci → content sniffing), i explicit registration w jednym punkcie.

## Mapa etapów

```
FAZA I — Fundament tekstowy (etapy 0-4)
  Stage 0: FileHandler Protocol + FormatRegistry        ~400 LOC  ✅
  Stage 1: Dokumenty (Markdown, RST, Text)               ~600 LOC  ✅
  Stage 2: Dane + Konfiguracja (CSV, JSON, Dockerfile)   ~800 LOC  ✅
  Stage 3: API + Infrastruktura (SQL, OpenAPI, K8s, GH)  ~1200 LOC ✅
  Stage 4: Pipeline fasada + CLI                          ~400 LOC  ✅

FAZA II — Multimodal Evidence Graph (etapy 5-7)
  Stage 5: Video Handler (PureCV RTSP, scene detection)   ~500 LOC  ✅
  Stage 6: Audio Handler (VAD, 3kHz telephony, μ-law)     ~550 LOC  ✅
  Stage 7: Evidence Graph (fusion, lazy retrieval)         ~450 LOC  ✅

FAZA III — Produkcja (etapy 8-10)
  Stage 8: VideoChatLogic (speaker+emotion fusion)        ~600 LOC  🔄
  Stage 9: Integracja z istniejącym code2logic            ~300 LOC  🔄
  Stage 10: Benchmarki + CLI multimodal                   ~400 LOC  🔄
```

Łącznie: ~6200 LOC nowego kodu (Fazy I-II ukończone: ~4900 LOC).

---

## FAZA I — Fundament Tekstowy

### Etap 0 — FileHandler Protocol + FormatRegistry (~400 LOC) ✅

Plik: `stage_0_foundation.py`

Definiuje trzy kluczowe abstrakcje. `FileLogic Protocol` — minimalny interfejs danych logicznych: `source_file`, `source_hash`, `file_category`, metody `to_dict()` i `complexity()`. `FileHandler Protocol` — jeden handler per typ pliku z metodami `parse()`, `to_spec()`, `reproduce()` i `sniff()`. `FormatRegistry` — centralny rejestr z dwuetapowym resolve: po rozszerzeniu znajdź kandydatów, po treści (sniff) wybierz najlepszego.

Dodatkowe komponenty: `SpecDetector` (wykrywa typ logiki z nagłówka spec — code/document/database/api/infra/data/config), `BaseHandlerMixin` (shared utilities: `_compute_hash`, `_read_content`, `_format_toon_header`).

Testy: 7/7 pass — Registry, SpecDetector, CodeLogicBase.

### Etap 1 — Handlery dokumentów (~600 LOC) ✅

Plik: `stage_1_document_handlers.py`

Trzy handlery: `MarkdownHandler` (sekcje z nagłówkami #, frontmatter YAML, code blocks, linki, obrazy), `TextHandler` (podział na paragrafy), `RstHandler` (nagłówki z podkreśleniami =, -, ~, ^). Model `DocumentLogic` definiuje: tytuł, język, sekcje (level, title, summary, word_count), frontmatter, metadata.

TOON output: jedna linia na sekcję — `"h1:Installation | Install via pip... | 80w"`.

Reprodukcja: tryb template (bez LLM) lub chunked reproduction (z LLM, podział po sekcjach).

Testy: 6/6 pass.

### Etap 2 — Dane i konfiguracja (~800 LOC) ✅

Plik: `stage_2_data_config_handlers.py`

Cztery handlery. `CsvHandler` — inferencja typów kolumn (int/float/bool/date/string) z próbek, detekcja delimitera przez `csv.Sniffer`, TOON: `"C[8]: id:int PK, name:str, email:str UNIQUE"`. `JsonDataHandler` — schemat z zagnieżdżeniami, negative sniffing (odrzuca package.json, tsconfig.json). `DockerfileHandler` — kategoryzacja instrukcji (build/runtime/network/security). `EnvHandler` — maskowanie wrażliwych zmiennych (KEY/SECRET/PASSWORD), kategoryzacja (database/network/security/runtime).

Testy: 3/3 pass — CSV type inference, .env masking, JSON schema.

### Etap 3 — API i infrastruktura (~1200 LOC) ✅

Plik: `stage_3_api_infra_handlers.py`

Cztery handlery z content sniffing. `SqlHandler` — parsuje CREATE TABLE z kolumnami, constraint-ami (PK, FK, UNIQUE, NN), wykrywa dialekt (postgresql/mysql/sqlite). `OpenApiHandler` — sniff: 0.7 dla `openapi:` lub `swagger:`, +0.2 dla `paths:`. `KubernetesHandler` — sniff: 0.5 dla `apiVersion:`, +0.3 dla `kind:`, +0.2 dla `metadata:`. `GithubActionsHandler` — sniff: 0.6 dla `.github/workflows` w ścieżce, +0.3 dla `on:` + `jobs:`.

Kluczowy test: disambiguation — na pliku `deployment.yaml` K8s handler wygrywa, na `ci.yml` GitHub Actions handler wygrywa, na `api.yaml` z `openapi:` OpenAPI handler wygrywa.

Testy: 4/4 pass.

### Etap 4 — Pipeline i CLI (~400 LOC) ✅

Plik: `stage_4_pipeline_cli.py`

Fasada `Pipeline` zastępuje cztery entry pointy reprodukcji: `to_spec()` (plik → spec), `reproduce()` (spec → plik), `roundtrip()` (pełny cykl), `batch()` (cały katalog), `formats()` (lista handlerów). CLI: `toonic spec <source>`, `toonic reproduce <spec>`, `toonic formats`.

Rejestracja 11 handlerów z etapów 0-3 w jednej funkcji `initialize_all_handlers()`.

Testy: 7/7 pass.

---

## FAZA II — Multimodal Evidence Graph

### Etap 5 — Video Handler PureCV (~500 LOC) ✅

Plik: `stage_5_video_handler.py`

Źródło: badanie "bez użycia ffmpeg, inne szybsze rozwiązania" — Pure OpenCV, zero FFmpeg/GPU.

Trzy komponenty. `LowQRTSPExtractor` — przechwytywanie strumieni RTSP z wielu kamer przez `cv2.VideoCapture`. Osobny daemon thread per kamera, rolling buffer (`deque maxlen=30` — 1 sekunda przy 30fps), natychmiastowy resize do 160x120 i JPEG Q=10 (~2.5 kB/klatkę). Synchronizacja buffer-based bez NTP — w momencie generowania segmentu pobieramy najnowszą klatkę z każdego bufora.

`SceneDetector` — detekcja zmian scen przez `cv2.absdiff()` z konfigurowalnym progiem (domyślnie 0.4 = 40% zmiany pikseli). 10x szybciej niż FFmpeg scene filter. Generuje `KeyframeSpec` z timestamp, score i base64 JPEG.

`VideoFileHandler` — implementuje `FileHandler Protocol`. Parsuje pliki video: odczytuje FPS, rozdzielczość, czas trwania, uruchamia `SceneDetector`, grupuje keyframes w 10-sekundowe segmenty. Generuje TOON z nagłówkiem (plik, czas, rozdzielczość, liczba keyframes) i listą segmentów.

Kompresja: 10s Full HD 30fps = 50 MB → 1 keyframe 160x120 Q=10 = 2.5 kB. Współczynnik ~400x.

Modele: `KeyframeSpec` (timestamp, camera_id, scene_change_score, b64_data), `VideoSegment` (index, start/end, keyframes, audio), `VideoLogic` (FileLogic + segments, total_keyframes, config lowQ).

Nowe CLI: `toonic spec video.mp4 --fmt toon`, `toonic spec "rtsp://cam1,rtsp://cam2" --multi-cam --duration 300`.

Testy: 6/6 pass.

### Etap 6 — Audio Handler VAD + Telephony (~550 LOC) ✅

Plik: `stage_6_audio_handler.py`

Źródło: badanie "audio z tej kamery — VAD, 3kHz telephony, μ-law" — PyAudio + webrtcvad + numpy.

Cztery komponenty. `SpeechDetector` — WebRTC VAD na 20ms ramkach audio, agresywność 0-3 (domyślnie 2), latency <0.1ms. Wykrywa segmenty mowy z konfigurowalnymi progami (`min_speech_s=0.3`, `min_silence_s=0.5`). Odrzuca ~80% czasu (cisza).

`TelephonyFilter` — FIR lowpass 3 kHz (pasmo telefoniczne ITU-T G.711) z oknem Hanninga, + downsampling 16 kHz → 8 kHz. Ludzka mowa zrozumiała w 300 Hz – 3400 Hz — obcięcie wyższych częstotliwości redukuje rozmiar o ~50%.

`MuLawCodec` — kompresja μ-law (G.711): PCM 16-bit → 8-bit. Percepcyjnie mowa brzmi prawie identycznie, bo μ-law zachowuje dynamikę w zakresie najczęściej występujących amplitud.

`AudioFileHandler` — implementuje `FileHandler Protocol`. Parsuje pliki WAV: odczytuje sample rate, channels, bitdepth, uruchamia VAD, kompresuje speech segments przez TelephonyFilter + MuLaw. Fallback bez webrtcvad: cały plik jako jeden segment.

Kompresja łączna: surowe 1s audio CD (32 kB) → VAD (odrzuca 80%) + 3 kHz lowpass + μ-law + downsample = 4 kB aktywnej mowy. Na minutę materiału: ~50 kB zamiast ~1.9 MB (~38x).

Modele: `SpeechSegment` (start/end, duration, energy_db, encoding, b64_data), `AudioLogic` (FileLogic + speech_segments, total_speech_s, speech_ratio, vad_aggressiveness).

Nowe CLI: `toonic spec meeting.wav --fmt toon --vad 2`, `toonic spec "rtsp://cam-audio" --speech-only`.

Testy: 6/6 pass (w tym μ-law round-trip i TelephonyFilter 16kHz→8kHz).

### Etap 7 — Evidence Graph: Multimodal Fusion (~450 LOC) ✅

Plik: `stage_7_evidence_graph.py`

Źródło: podsumowanie projektu v4.2 — "Evidence Graph: indeks + low-q próbki + lazy retrieval".

Trzy komponenty. `EvidenceNode` — pojedynczy węzeł dowodowy: id (np. `code:auth.py:validate_token`), category (code/document/audio/video/test/database), timestamp, summary, lowq_data (base64), source_path (lazy retrieval pointer), related_to (lista powiązanych node ids).

`EvidenceGraphBuilder` — buduje graf z wyników handlerów etapów 0-6: `add_code_evidence()`, `add_document_evidence()`, `add_video_evidence()`, `add_audio_evidence()`, `add_database_evidence()`, `add_test_evidence()`. Automatyczne linkowanie relacji: węzły z tego samego pliku są powiązane, węzły z podobnym timestamp (±5s) są powiązane, code ↔ test z tym samym modułem są powiązane.

`EvidenceGraphHandler` — implementuje `FileHandler Protocol`. Generuje TOON Evidence Graph: nagłówek z liczbą źródeł i węzłów, statystyki per kategoria, lista węzłów pogrupowana per kategoria (max 20 w indeksie), relacje (top 20 linków).

Evidence Graph TOON ma trzy warstwy. Warstwa indeksowa (~1-5 kB): nagłówek, statystyki, lista node IDs. Warstwa próbek (~10-100 kB/h): low-quality dane inline (keyframes, μ-law audio, compressed spec). Warstwa referencyjna (~1 kB): ścieżki do pełnych danych + offsety bajtowe dla lazy retrieval.

Nowe CLI: `toonic evidence ./project/ --sources "src/ docs/ tests/"`, `toonic evidence "rtsp://cam1,rtsp://cam2" --duration 600 --vad`.

Testy: 10/10 pass — EvidenceNode, Builder z 6 typami dowodów, auto-linkowanie relacji, TOON generation z 5 kategoriami.

---

## FAZA III — Produkcja (planowane)

### Etap 8 — VideoChatLogic (~600 LOC) 🔄

Model `VideoChatLogic` łączy dane z `VideoLogic` i `AudioLogic` w kontekście rozmowy video (Zoom, Teams, Google Meet). Nowe komponenty: speaker diarization (przypisanie mowy do osoby na podstawie pozycji w kadrze + timing audio), gesture/emotion hints (detekcja gestów — wskazywanie, kiwanie — na podstawie różnic między klatkami, bez modelu AI), fused timeline segments (segment = kto mówi + z jaką emocją + na co wskazuje + co mówi).

Przykładowy TOON:
```
CS0[2.3s]: Alice:speech | cam0:excited/pointing | cam1:Bob:nodding
  audio:μ-law:11.2kB | fused:"Alice wyjaśnia architekturę SQL"
```

Szacowane tokeny: ~40k na godzinę spotkania (vs 1.2 GB surowego video).

### Etap 9 — Integracja z istniejącym code2logic (~300 LOC) 🔄

Modyfikacje istniejących plików: `universal.py` — delegacja do `FormatRegistry` dla nie-kodowych plików (10 linii). `base.py` — dodanie `sniff()` do `BaseParser` (5 linii). `cli.py` — nowe komendy `spec`, `reproduce`, `evidence`, `formats` (100 linii). `reproducer.py` — rozszerzenie `SpecReproducer` o `reproduce_from_spec()` z autodetekcją formatu (30 linii). `__init__.py` — reeksport nowych klas.

Zasada: zero breaking changes. Istniejące `code2logic ./project/` działa identycznie. Nowe komendy (`toonic spec`, `toonic evidence`) to dodatki.

### Etap 10 — Benchmarki + CLI multimodal (~400 LOC) 🔄

Benchmarki: porównanie handlerów etapów 1-3 z istniejącymi generatorami (TOON, YAML, JSON) na tych samych plikach. Metryki: token efficiency (score/1000 tokens), reproduction accuracy, parse time, spec size.

Benchmarki multimodal: kompresja video (ratio, keyframe quality), audio (speech detection accuracy, compression ratio), Evidence Graph (total size, node coverage, relation precision).

CLI multimodal: `toonic spec video.mp4 --lowq 160x120:10`, `toonic spec meeting.wav --vad 2 --telephony`, `toonic evidence ./project/ --multi-cam "rtsp://cam1,cam2" --vad`.

---

## Podsumowanie kosztów

| Faza | Etapy | LOC | Status |
|------|-------|-----|--------|
| I — Fundament tekstowy | 0-4 | ~3400 | ✅ Ukończone |
| II — Multimodal Evidence Graph | 5-7 | ~1500 | ✅ Ukończone |
| III — Produkcja | 8-10 | ~1300 | 🔄 Planowane |
| **Łącznie** | **0-10** | **~6200** | **79% ukończone** |

## Mapa migracji z code2logic

| Istniejący komponent | Zastępuje/rozszerza |
|---------------------|---------------------|
| `universal.py reproduce_file()` | `Pipeline.to_spec()` + `Pipeline.reproduce()` |
| `reproducer.py SpecReproducer` | `Pipeline.reproduce()` |
| `reproduction.py CodeReproducer` | `Pipeline.roundtrip()` |
| `project_reproducer.py` | `Pipeline.batch()` |
| `base.py BaseParser` | `FileHandler Protocol` |
| `models.py` (296 LOC) | split → `core/logic/*.py` per category |
| `generators.py` (1787 LOC) | `handler.to_spec()` per handler |
| `cli.py` (909 LOC) | uproszczone CLI (~200 LOC) |
| *(nowe)* | `LowQRTSPExtractor` → video pipeline |
| *(nowe)* | `SpeechDetector` + `MuLawCodec` → audio pipeline |
| *(nowe)* | `EvidenceGraphBuilder` → multimodal fusion |

## Architektura docelowa

```
toonic/
├── core/
│   ├── __init__.py          ← FileLogic, FileHandler Protocols
│   └── logic/
│       ├── code.py          ← CodeLogic (istniejący, rozszerzony)
│       ├── document.py      ← DocumentLogic
│       ├── data.py          ← TableLogic, JsonSchemaLogic
│       ├── config.py        ← ConfigLogic
│       ├── database.py      ← SqlSchemaLogic
│       ├── api.py           ← ApiLogic
│       ├── infra.py         ← InfraLogic
│       ├── video.py         ← VideoLogic, KeyframeSpec, VideoSegment
│       ├── audio.py         ← AudioLogic, SpeechSegment
│       └── evidence.py      ← EvidenceGraph, EvidenceNode
├── formats/
│   ├── __init__.py          ← FormatRegistry + registration
│   ├── _base.py             ← BaseHandlerMixin
│   ├── document.py          ← Markdown/Text/RST handlers
│   ├── data.py              ← CSV/JSON-data handlers
│   ├── config.py            ← Env/Dockerfile handlers
│   ├── api.py               ← OpenAPI/GraphQL handlers
│   ├── infra.py             ← K8s/Terraform handlers
│   ├── cicd.py              ← GH Actions/GitLab CI handlers
│   ├── database.py          ← SQL handler
│   ├── video.py             ← VideoFile/RTSP handlers
│   ├── audio.py             ← Audio/VAD handler
│   └── evidence.py          ← Evidence Graph handler
├── multimodal/
│   ├── rtsp_extractor.py    ← LowQRTSPExtractor
│   ├── scene_detector.py    ← SceneDetector (PureCV)
│   ├── speech_detector.py   ← SpeechDetector (WebRTC VAD)
│   ├── telephony.py         ← TelephonyFilter + MuLawCodec
│   └── fusion.py            ← EvidenceGraphBuilder
├── pipeline.py              ← Pipeline fasada
└── cli.py                   ← Uproszczone CLI
```

## Zależności

```
CORE (zero deps):       Python 3.10+ stdlib + dataclasses
DOCUMENTS (zero deps):  stdlib only
DATA/CONFIG (zero deps): stdlib + csv + json + tomllib
API/INFRA (1 dep):      pyyaml
VIDEO (1 dep):           opencv-python (pip install opencv-python)
AUDIO (2 deps):          numpy + webrtcvad (opcjonalnie pyaudio)
ALL OPTIONAL:            Każdy handler sprawdza dostępność → graceful fallback
```

## Kompresja per domena

| Domena | Surowe dane | Po kompresji TOON | Współczynnik | Tokeny/h |
|--------|-------------|-------------------|-------------|----------|
| Kod (AST) | ~200 kB/moduł | ~5 kB TOON | ~40x | ~50k |
| Dokumenty | ~50 kB/doc | ~2 kB TOON | ~25x | ~20k |
| Audio (VAD+μ-law) | 1.9 MB/min | ~50 kB/min | ~38x | ~15k |
| Video (PureCV) | 50 MB/10s | 2.5 kB/keyframe | ~400x | ~25k |
| Multi-cam | 6 GB/10min | ~2 MB TOON | ~3000x | ~50k |
| Evidence Graph | GB+ projekt | 10-100 kB indeks | ~95-99.9% | index only |

---

*Plan refaktoryzacji v4.2 — od kodu do multimodalnego Evidence Graph. 8 etapów ukończonych, 3 w planach. Architektura addytywna: zero breaking changes.*
