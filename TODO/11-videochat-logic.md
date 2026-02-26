---
title: "Toonic VideoChatLogic — Fuzja Mowy i Gestów w Spotkaniach Video"
slug: toonic-videochat-logic
date: 2026-02-26
author: WronAI
categories: [projekty, toonic, multimodal]
tags: [video-chat, speaker-diarization, emotion, gesture, meetings, fusion, Zoom, Teams]
excerpt: "VideoChatLogic to model fuzji audio+video w kontekście rozmów — kto mówi, z jaką emocją, na co wskazuje. Bez AI preprocessing: pure pixel diff + VAD timing = speaker segments. 40k tokenów na godzinę spotkania zamiast 1.2 GB surowego materiału."
featured_image: toonic-videochat-fusion.png
---

# Toonic VideoChatLogic — Fuzja Mowy i Gestów w Spotkaniach Video

## Problem: spotkania video to ocean danych

Godzinne spotkanie na Zoom to ~1.2 GB surowego materiału: dwa strumienie video (ekran + kamera) + audio. Podanie tego LLM-owi jest niemożliwe. Ale LLM nie potrzebuje każdej klatki — potrzebuje wiedzieć kto mówił, kiedy, z jakim nastawieniem i o czym.

## Podejście: fuzja bez AI

VideoChatLogic łączy wyniki z `VideoLogic` (etap 5) i `AudioLogic` (etap 6) w kontekście spotkania. Kluczowa innowacja: nie używamy modeli rozpoznawania twarzy ani analizy sentymentu. Zamiast tego operujemy na surowych sygnałach — timing mowy (VAD) + zmiany w kadrze (pixel diff) + pozycja ruchu w klatce.

Speaker diarization opiera się na korelacji: gdy VAD wykrywa mowę, sprawdzamy która część kadru wykazuje największy ruch (mowa = ruch warg/głowy). Gesture hints to analiza kierunku i amplitudy ruchu w klatce — szybki ruch w górę/dół = kiwanie, ruch na boki = wskazywanie.

## Model VideoChatLogic

Każdy segment fuzji zawiera: timestamp, speaker_id (na podstawie pozycji w kadrze), speech_duration, gesture_type (nodding/pointing/still), scene_context (screen_share/face/group), oraz audio w formacie μ-law i keyframe w lowQ.

Wynikowy TOON wygląda tak: `CS0[2.3s]: Alice:speech | cam0:excited/pointing | cam1:Bob:nodding | audio:μ-law:11.2kB | fused:"Alice wyjaśnia architekturę SQL"`.

## Wartość biznesowa

Automatyczne minutki z kontekstem: nie tylko co zostało powiedziane, ale kto mówił, z jakim zaangażowaniem (dużo gestów = wysoka energia), i w jakim kontekście wizualnym (screen share = demo, face-to-face = dyskusja). LLM dostaje 40k tokenów zamiast 1.2 GB i może wygenerować pełne podsumowanie spotkania z action items.

## Status

VideoChatLogic jest planowana jako etap 8 roadmapy refaktoryzacji. Bazuje na ukończonych etapach 5 (VideoHandler) i 6 (AudioHandler). Szacowany nakład: ~600 LOC.

---

*VideoChatLogic — od pikseli i waveformów do "kto, co, jak" w spotkaniach. Zero AI preprocessing.*
