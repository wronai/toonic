---
title: "Toonic Multimodal — Video z Wielu Kamer do Formatu TOON"
slug: toonic-multimodal-video
date: 2026-02-26
author: WronAI
categories: [projekty, toonic, multimodal]
tags: [video, RTSP, OpenCV, keyframes, scene-detection, edge, multi-cam]
excerpt: "Toonic rozszerza się o przetwarzanie strumieni video z wielu kamer RTSP. Pipeline PureCV extrahuje keyframes przy zmianach scen, kompresuje do 160x120 Q=10 i generuje spec TOON — 400x mniejszy niż oryginał, gotowy dla LLM."
featured_image: toonic-video-pipeline.png
---

# Toonic Multimodal — Video z Wielu Kamer do Formatu TOON

## Problem: video jest za duże dla LLM

Jeden strumień Full HD z kamery RTSP to ~50 MB na 10 sekund. Podanie tego LLM-owi jest niemożliwe — ani kosztowo, ani technicznie. Ale LLM nie potrzebuje 3000 klatek, żeby zrozumieć co się dzieje. Potrzebuje jednej kluczowej klatki na zmianę sceny, w niskiej jakości wystarczającej do rozpoznania kontekstu.

## Podejście: surowe dane, nie AI preprocessing

Kluczowa decyzja architektoniczna Toonic: nie używamy Whisper, YOLO ani żadnego modelu AI do preprocessingu. Zamiast tego ekstrahjujemy surowe dane w niskiej jakości i pozwalamy LLM analizować je bezpośrednio. To oznacza zero zależności od GPU, działanie na edge devices (RPi4) i pełną kontrolę nad tym, co trafia do modelu.

## Pipeline: RTSP → keyframes → TOON

Pipeline składa się z trzech kroków. Pierwszy to capture — przechwycenie strumieni z kamer RTSP przez OpenCV VideoCapture z buforami rolling (deque maxlen=30 dla 1s przy 30fps). Drugi to scene detection — porównanie kolejnych klatek przez `cv2.absdiff()` z progiem 0.4 (40% zmiany pikseli). Trzeci to kompresja — resize do 160x120 + JPEG quality=10, co daje ~2.5 kB na klatkę zamiast ~150 kB przy Full HD.

Wynik kompresji jest dramatyczny: 10-sekundowy segment Full HD 30fps zajmujący 50 MB zostaje zredukowany do jednej kluczowej klatki o wadze 2.5 kB — współczynnik kompresji ~400x.

## Synchronizacja wielu kamer

Synchronizacja strumieni z wielu kamer odbywa się bez NTP — każda kamera ma osobny wątek przechwytywania z buforem. W momencie generowania segmentu TOON pobieramy najnowszą klatkę z każdego bufora. To prosty mechanizm buffer-based sync, który działa nawet przy różnicach latency między kamerami do ~100ms.

## Format TOON dla video

Wynikowy spec TOON dla materiału multi-cam wygląda tak: nagłówek z liczbą kamer i segmentów, a każdy segment zawiera timestamp, klatki z kamer jako base64 JPEG i opcjonalnie audio. Cały 10-minutowy materiał z dwóch kamer mieści się w ~2 MB zamiast ~6 GB surowego video.

## Technologie

Cały pipeline używa wyłącznie: OpenCV (RTSP capture, resize, JPEG encode, scene diff), stdlib Python (threading, base64, collections.deque) i numpy (opcjonalnie, dla pixel diff). Zero FFmpeg, zero GPU, CPU 5-15% nawet na RPi4.

## Integracja z ekosystemem Toonic

Video handler integruje się z istniejącą architekturą Toonic przez `FileHandler Protocol`: metoda `parse()` przyjmuje ścieżkę do pliku video lub URL RTSP, `to_spec()` generuje TOON z keyframes, a `reproduce()` może odtworzyć sekwencję klatek z opisu.

Szczegóły implementacji dostępne w pliku `stage_5_video_handler.py` w repozytorium Toonic.

---

*Toonic Multimodal — przetwarzanie video bez AI, gotowe na edge devices.*
