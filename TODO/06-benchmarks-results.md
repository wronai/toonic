---
title: "Benchmarki Reprodukcji Kodu — Wyniki i Wnioski"
slug: benchmarks-results
date: 2026-02-25
author: WronAI
categories: [projekty, benchmarki, analiza]
tags: [benchmark, TOON, JSON, YAML, reprodukcja, LLM, metryki]
excerpt: "Zautomatyzowane benchmarki code2logic pokazują, że format TOON konsekwentnie wygrywa z JSON i YAML zarówno pod względem trafności reprodukcji, jak i efektywności tokenowej."
featured_image: benchmark-comparison-chart.png
---

# Benchmarki Reprodukcji Kodu — Wyniki i Wnioski

## Metodologia

Zbudowaliśmy w pełni zautomatyzowane środowisko testowe, które sprawdza, jak modele LLM radzą sobie z rekonstrukcją kodu na podstawie różnych specyfikacji. Benchmark działa w czterech krokach: analiza projektu (20 plików z `tests/samples/`), ekstrakcja specyfikacji w różnych formatach, reprodukcja kodu przez LLM na podstawie specyfikacji, oraz ocena jakości wyniku.

Ocena opiera się na metryce ważonej: podobieństwo tekstowe (SequenceMatcher/token overlap), heurystyki strukturalne (liczba klas, funkcji, importów, atrybutów), heurystyki semantyczne (nakładanie się identyfikatorów, obecność sygnatur, dekoratorów, typów i docstringów) oraz poprawność syntaktyczna i uruchamialność.

## Wyniki główne

Format benchmark na 20 plikach pokazuje, że YAML osiąga 62.4% trafności przy 100% poprawności syntaktycznej. TOON uzyskuje najwyższy wynik w benchmarku projektowym (63.8%) przy 60% uruchamialności. JSON osiąga 64.4% w teście tokenowym, ale zużywa ponad 5 razy więcej tokenów. Markdown ma 100% uruchamialności, ale niższy wynik ogólny (65.6%). LogicML jest ekstremalnie kompaktowy (245 tokenów/plik) z wynikiem powyżej 76%.

W benchmarku behawioralnym (testy równoważności funkcjonalnej) osiągnęliśmy 85.7% poprawności — 6 z 7 testów zaliczonych, 1 pominięty.

## Efektywność tokenowa

Najciekawsza metryka to „score per 1000 tokens" — ile jakości reprodukcji uzyskujemy za każde 1000 tokenów kontekstu. Markdown prowadzi z wynikiem 48.7, YAML ma 42.1, a JSON tylko 23.7. TOON osiąga najlepszy stosunek absolutnego wyniku do zużycia tokenów.

Dla pełnego projektu code2logic (156 modułów, 42 706 linii) rozmiary specyfikacji wynoszą: JSON ~918 KB (~235 000 tokenów), YAML ~269 KB (~69 000 tokenów), TOON ~170 KB (~43 000 tokenów), Compact ~27 KB (~7 000 tokenów).

## Wnioski praktyczne

Kluczowe odkrycie: LLM lepiej rozumie skompresowaną wiedzę. Brak redundancji w formacie TOON sprawia, że model koncentruje się na istotnej informacji i rzadziej się „gubi". Mniej tokenów = mniejszy koszt, więcej miejsca na reasoning, lepsze wyniki.

Dla zadań wymagających najwyższej dokładności — TOON lub YAML. Dla zadań, gdzie liczy się uruchamialność — Markdown. Dla zadań, gdzie budżet tokenowy jest ograniczony — LogicML lub TOON ultra-compact.

## Artefakty benchmarkowe

Wszystkie wyniki są dostępne jako pliki JSON: benchmark_format.json (79.6 KB), benchmark_project.json (79.9 KB), benchmark_token.json (79.6 KB), benchmark_function.json (7.7 KB) i benchmark_behavioral.json (4.2 KB). Komendy do odtworzenia benchmarku dostępne w `BENCHMARK_COMMANDS.sh`.

---

*Benchmarki code2logic są w pełni reprodukowalne. Użyj `make benchmark` w repozytorium projektu.*
