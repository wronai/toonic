# Toonic — Refactoring Stages

Implementacja etapowa transformacji code2logic → Toonic v4.2 (Evidence Graph).

## Pliki

| Plik | Etap | Opis | LOC | Testy |
|------|------|------|-----|-------|
| `stage_0_foundation.py` | 0 | FileHandler Protocol, FormatRegistry, SpecDetector | ~400 | 7/7 ✅ |
| `stage_1_document_handlers.py` | 1 | Markdown, Text, RST handlers + DocumentLogic | ~600 | 6/6 ✅ |
| `stage_2_data_config_handlers.py` | 2 | CSV, JSON-data, Dockerfile, .env handlers | ~800 | 3/3 ✅ |
| `stage_3_api_infra_handlers.py` | 3 | SQL, OpenAPI, Kubernetes, GitHub Actions handlers | ~1200 | 4/4 ✅ |
| `stage_4_pipeline_cli.py` | 4 | Pipeline fasada, CLI, handler registration | ~400 | 7/7 ✅ |
| `stage_5_video_handler.py` | 5 | PureCV RTSP, scene detection, multi-cam sync | ~500 | 6/6 ✅ |
| `stage_6_audio_handler.py` | 6 | VAD speech, 3kHz telephony, μ-law compression | ~550 | 6/6 ✅ |
| `stage_7_evidence_graph.py` | 7 | Evidence Graph builder, multimodal fusion | ~450 | 10/10 ✅ |

**Łącznie: ~4900 LOC, 49 testów**

## Architektura

```
FAZA I — Tekstowa (etapy 0-4): kod, dokumenty, dane, API, infra → TOON
FAZA II — Multimodal (etapy 5-7): video + audio + fusion → Evidence Graph
FAZA III — Produkcja (etapy 8-10): VideoChatLogic, integracja, benchmarki
```

## Uruchomienie testów

```bash
# Każdy stage ma wbudowane testy
python stage_0_foundation.py          # 7 testów
python stage_1_document_handlers.py   # 6 testów
python stage_2_data_config_handlers.py # 3 testy
python stage_3_api_infra_handlers.py  # 4 testy
python stage_4_pipeline_cli.py        # 7 testów
python stage_5_video_handler.py       # 6 testów (bez OpenCV = structure only)
python stage_6_audio_handler.py       # 6 testów (μ-law+filter z numpy)
python stage_7_evidence_graph.py      # 10 testów
```

## Zależności

```
Core (stages 0-4):  Python 3.10+ stdlib only
Video (stage 5):    opencv-python
Audio (stage 6):    numpy + webrtcvad (opcjonalnie pyaudio)
Evidence (stage 7): żadne dodatkowe
```

## Kompresja per domena

| Domena | Surowe | TOON | Ratio |
|--------|--------|------|-------|
| Kod (AST) | 200 kB/moduł | 5 kB | ~40x |
| Dokumenty | 50 kB/doc | 2 kB | ~25x |
| Audio (VAD) | 1.9 MB/min | 50 kB/min | ~38x |
| Video (PureCV) | 50 MB/10s | 2.5 kB/kf | ~400x |
| Multi-cam | 6 GB/10min | 2 MB | ~3000x |
