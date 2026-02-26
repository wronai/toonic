---
title: "Evidence Graph — Multimodalny Kompresor Dowodowy dla LLM"
slug: evidence-graph-multimodal
date: 2026-02-26
author: WronAI
categories: [projekty, toonic, evidence-graph, architektura]
tags: [evidence-graph, multimodal, LLM, kompresja, lazy-retrieval, fusion]
excerpt: "Evidence Graph to architektura TOON v4.x, w której indeks + low-quality próbki + lazy retrieval tworzą pipeline dowodowy dla LLM. Kod, dokumenty, audio, video i multi-cam w jednym prompcie — 95-99.9% oszczędności tokenów."
featured_image: evidence-graph-architecture.png
---

# Evidence Graph — Multimodalny Kompresor Dowodowy dla LLM

## Ewolucja: od refaktoryzacji kodu do AI nervous system

Code2Logic zaczął jako narzędzie do kompresji kodu źródłowego. Toonic rozszerzył to na dokumenty, konfiguracje, schematy baz danych i infrastrukturę. Evidence Graph to kolejny krok — architektura, w której każdy typ danych (kod, dokumenty, audio, video, strumienie multi-cam, czaty video) jest kompresowany do wspólnego formatu TOON i łączony w graf dowodowy.

Zasada jest prosta: LLM nie czyta surowych gigabajtów. Dostaje lekki indeks, a gdy potrzebuje dowodu — dociąga konkretny fragment w niskiej jakości. Wystarczającej, żeby rozumować.

## Architektura Evidence Graph

Graf składa się z trzech warstw. Warstwa indeksowa to nagłówek TOON z metadanymi: ile kamer, ile segmentów, timeline, kluczowe zdarzenia. Zajmuje ~1-5 kB.

Warstwa próbek to low-quality dane: keyframes 160x120 Q=10 (video), waveformy 8 kHz μ-law (audio), streszczenia sekcji (dokumenty), sygnatury funkcji (kod). Zajmuje ~10-100 kB na godzinę materiału.

Warstwa referencyjna to wskaźniki do pełnych danych: ścieżki plików, offsety czasowe, zakresy bajtów. LLM może poprosić o dociągnięcie konkretnego fragmentu w wyższej jakości — to lazy retrieval.

## Modele logiki per domena

Każda domena ma dedykowany model logiki, ale wszystkie implementują wspólny `FileLogic Protocol`:

**CodeLogic** — AST + symbole, sygnatury, zależności. Kompresja AST→TOON, ~50k tokenów/h pracy nad kodem.

**DocumentLogic** — sekcje + streszczenia + cytaty. Chunk + summary, ~20k tokenów/h czytania.

**AudioLogic** — VAD speech segments, 3 kHz μ-law waveform. ~15k tokenów/h nagrania.

**VideoLogic** — keyframes przy zmianach scen, 160x120 Q=10. ~25k tokenów/h materiału.

**MultiStreamLogic** — zsynchronizowane keyframes z wielu kamer, fused timeline. ~50k tokenów/h.

**VideoChatLogic** — speaker diarization, detekcja emocji/gestów z klatek, fuzja audio+video. ~40k tokenów/h spotkania.

## Pipeline przetwarzania

Przepływ danych w Evidence Graph: INPUT (RTSP cams/audio, pliki, repozytoria) → EXTRACT (keyframes przy scene_change, VAD speech, AST parse) → COMPRESS (160x120 Q=10, 8 kHz μ-law, TOON spec) → SYNC (timestamp buffers, multi-cam alignment) → TOON (Evidence Graph z indeksem + referencjami) → LLM (mały indeks, lazy dociąganie dowodów).

## Zastosowania biznesowe

CI/CD: walidacja schematu + testy + security w jednym prompcie — cross-domain reasoning z TOON kodu, raportu testów, skanera bezpieczeństwa i migracji SQL.

Spotkania: fuzja audio (mowa) + video (gesty, emocje) → automatyczne minutki z kontekstem wizualnym. Kto mówił, z jaką emocją, na co wskazywał.

Bezpieczeństwo: multi-cam VAD — detekcja anomalii na podstawie zsynchronizowanych strumieni. Ruch + dźwięk + zmiana sceny.

Edge AI: RPi4 z lowQ RTSP → lokalne AI bez chmury. Przetwarzanie na urządzeniu, wysyłanie do LLM tylko istotnych segmentów.

## Status implementacji

Evidence Graph jest zaimplementowany w etapach 5-7 planu refaktoryzacji Toonic: Stage 5 (VideoHandler + scene detection), Stage 6 (AudioHandler + VAD + μ-law), Stage 7 (EvidenceGraphHandler + multi-stream fusion + lazy retrieval). Każdy etap jest addytywny i nie łamie istniejących testów.

---

*Evidence Graph — od kodu do multimodalnego AI nervous system. 95-99.9% oszczędności tokenów.*
