---
title: "Toonic Audio — VAD Speech Detection i Kompresja Telefoniczna"
slug: toonic-audio-vad-speech
date: 2026-02-26
author: WronAI
categories: [projekty, toonic, multimodal, audio]
tags: [audio, VAD, webrtcvad, speech, telephony, mu-law, PyAudio, edge]
excerpt: "Toonic ekstrahuję mowę ze strumieni RTSP kamer za pomocą WebRTC VAD, obcina do pasma telefonicznego 3kHz, kompresuje μ-law — i wysyła do LLM tylko to co istotne. 85% mniej segmentów, 4 kB/s zamiast 32 kB/s."
featured_image: toonic-audio-vad.png
---

# Toonic Audio — VAD Speech Detection i Kompresja Telefoniczna

## Problem: 90% audio to cisza

W typowym nagraniu ze spotkania lub monitoringu, mowa stanowi zaledwie 10-20% czasu. Reszta to cisza, szum tła, odgłosy otoczenia. Wysyłanie tego do LLM to marnotrawstwo tokenów i kontekstu.

## Rozwiązanie: Voice Activity Detection + Telephony Band

Pipeline audio Toonic działa w trzech etapach. Pierwszy to VAD (Voice Activity Detection) — biblioteka WebRTC VAD analizuje 20ms ramki audio i klasyfikuje je jako mowę lub ciszę z latencją poniżej 0.1ms. Agresywność detekcji jest konfigurowalna (0-3), domyślnie 2.

Drugi etap to obcięcie do pasma telefonicznego 3 kHz. Ludzka mowa zrozumiała jest w zakresie 300 Hz – 3400 Hz — to standard ITU-T G.711 używany w telefonii. Obcięcie wyższych częstotliwości redukuje rozmiar danych o ~50% bez utraty zrozumiałości.

Trzeci etap to kompresja μ-law (mu-law) — algorytm kompandowania z G.711, który redukuje rozdzielczość z 16 bitów do 8 bitów. Percepcyjnie mowa brzmi prawie identycznie, bo μ-law zachowuje dynamikę w zakresie najczęściej występujących amplitud.

## Wynikowa kompresja

Surowe audio 1 sekundy w jakości CD (16 kHz, 16 bit, mono) zajmuje 32 kB. Po przejściu przez pipeline VAD + 3 kHz lowpass + μ-law + downsampling do 8 kHz zostaje 4 kB. A ponieważ VAD odrzuca ~80% czasu (cisza), efektywna kompresja na minutę materiału to ~50 kB zamiast ~1.9 MB — współczynnik ~38x.

## Biblioteki

Cały pipeline audio używa: PyAudio (capture z mikrofonu kamery lub strumienia RTSP), webrtcvad (VAD — C extension, ultra-szybki), numpy (FIR lowpass filter + μ-law kompresja). Opcjonalnie wave ze stdlib do generowania nagłówków WAV.

## Speech-Triggered TOON

Kluczowa innowacja: segmenty TOON są generowane tylko gdy wykryto mowę. Zamiast regularnego samplingowania co N sekund, system czeka na aktywność głosową i dopiero wtedy tworzy segment z audio + zsynchronizowaną klatką video. W rezultacie 10-minutowe nagranie spotkania z ~2 minutami efektywnej mowy generuje ~24 segmenty zamiast ~120 — 85% redukcja.

## Integracja z Video Pipeline

Klasa `MultiModalLowQ` łączy `LowQRTSPExtractor` (video) z `RTSPVoiceExtractor` (audio). Gdy VAD wykryje mowę, system pobiera zsynchronizowaną klatkę video z bufora — tworząc pełny multimodalny segment TOON z waveformem audio i kontekstem wizualnym.

---

*Toonic Audio — tylko mowa, tylko istotne dane, edge-ready.*
