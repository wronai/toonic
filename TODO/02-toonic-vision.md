---
title: "Toonic — Uniwersalny Format Przenośny dla Ery LLM"
slug: toonic-vision
date: 2026-02-25
author: WronAI
categories: [projekty, toonic, wizja]
tags: [toonic, TOON, format, LLM, kompresja, portable]
excerpt: "Toonic to ewolucja code2logic — platforma, w której format TOON staje się uniwersalnym nośnikiem danych przenośnych: od kodu źródłowego i dokumentów, przez konfiguracje i schematy baz danych, po archiwa całych projektów."
featured_image: toonic-universal-format.png
---

# Toonic — Uniwersalny Format Przenośny dla Ery LLM

## Geneza: od code2logic do Toonic

Code2Logic zaczął jako narzędzie do konwersji kodu źródłowego w specyfikacje logiczne. Podczas pracy nad nim odkryliśmy coś fundamentalnego: zasada „wyekstrahuj strukturę, zapisz kompaktowo, odtwórz z LLM" nie ogranicza się do kodu. Każdy plik, który ma powtarzalną strukturę — od Dockerfile przez schemat SQL po prezentację PowerPoint — może przejść ten sam pipeline.

Z tego odkrycia rodzi się **Toonic**: platforma, w której format TOON (Token-Oriented Object Notation) pełni rolę **uniwersalnego formatu przenośnego** — jednego nośnika dla danych z dowolnego źródła.

## Filozofia: „Każdy plik ma logikę"

Centralną zasadą Toonic jest przekonanie, że każdy plik posiadający jakąkolwiek powtarzalną strukturę może być reprezentowany jako spec w formacie TOON. Nie chodzi o dosłowne kopiowanie — chodzi o ekstrakcję logiki i znaczenia, a następnie ich kompresję do minimum potrzebnego, by LLM (lub człowiek) mógł odtworzyć oryginał.

Tę filozofię realizujemy w trzech wymiarach: typ pliku wejściowego (co parsujemy), format logiki (plik pośredni w TOON), oraz format wyjściowy (co odtwarzamy lub transpilujemy).

## Co TOON zmienia w praktyce?

Format TOON osiąga 5-krotną redukcję rozmiaru w porównaniu z JSON przy zachowaniu — a często nawet poprawieniu — jakości rozumienia przez modele LLM.

Dla projektu z 156 modułami i 42 706 liniami kodu: JSON zajmuje ~918 KB (~235 000 tokenów), a TOON tylko ~170 KB (~43 000 tokenów). W praktyce oznacza to, że ten sam model LLM może przetworzyć 5 razy większy projekt lub że mniejszy (tańszy) model wystarczy do zadania, które wcześniej wymagało dużego.

TOON uzyskał 82.7% trafności reprodukcji kodu w benchmarkach projektowych — lepiej niż JSON (73.5%) i YAML (71.1%). Brak redundancji formatu sprawia, że model rzadziej się „gubi".

## Mapa zastosowań według rozmiaru modelu

Kluczową wartością Toonic jest obniżenie wymagań kognitywnych zadania. Dzięki temu mniejszy model może wykonać pracę, która wcześniej wymagała dużego.

Modele 3B–7B (lokalne, offline, edge) sprawdzają się przy klasyfikacji plików, wykrywaniu anomalii w strukturze, generowaniu docstringów i lokalizowaniu źródła bugów — pod warunkiem, że dostaną spec w TOON zamiast surowego kodu.

Modele 8B–30B radzą sobie z refaktoryzacją na poziomie modułu, generowaniem testów z logic2test, code review architektonicznym i dokumentacją techniczną. TOON całego projektu (~43k tokenów) mieści się w oknie kontekstowym 30B modelu, co jest niemożliwe przy surowym JSON.

Modele 70B–120B mogą realizować refaktoryzację całego projektu, architektoniczne decision making, generowanie pełnych implementacji i cross-format analizę — łączenie TOON kodu, schematu SQL i raportu testów w jednym prompcie.

## Zakres formatu przenośnego

Toonic obsługuje (lub planuje obsługiwać) następujące kategorie danych:

Kod źródłowy — istniejąca funkcjonalność code2logic: Python, JavaScript, TypeScript, Java, Go, Rust, C#.

Dokumenty tekstowe — Markdown, reStructuredText, AsciiDoc, PDF, DOCX. Każdy dokument jest rozbijany na sekcje z podsumowaniami i metadanymi.

Dane strukturalne — CSV, JSON-data, XML, TOML. Schemat i próbki danych kompresowane do kompaktowego spec.

Konfiguracja — Dockerfile, .env, pyproject.toml, Makefile, docker-compose. Deklaratywna logika konfiguracji w kilku liniach TOON.

API i schematy — OpenAPI, GraphQL, Protobuf, JSON Schema. Endpointy, typy, walidacja.

Infrastruktura — Terraform, Kubernetes, Ansible, Helm, CI/CD (GitHub Actions, GitLab CI). Zasoby, zależności, pipeline'y.

Bazy danych — SQL DDL/DML, migracje, ORM (Prisma, SQLAlchemy, Django). Tabele, relacje, indeksy.

Testy i bezpieczeństwo — JUnit/pytest XML, coverage, raporty Trivy/Snyk. Wyniki, priorytety napraw.

Pliki Office — Excel (arkusze, formuły, wykresy), PowerPoint (slajdy, layout), notebooki Jupyter.

## Cross-domain reasoning

Największa wartość Toonic ujawnia się przy analizie krzyżowej. Mały model 7B może walidować spójność między `schema.prisma` a `TEST-results.xml` — oba sprowadzone do TOON zajmują łącznie ~500 tokenów.

Duży model 70B+ może odpowiedzieć na pytanie „czy moja aplikacja jest gotowa do produkcji?", mając w jednym prompcie TOON kodu, raportu bezpieczeństwa, coverage XML i migracji SQL — łącznie ~30k tokenów zamiast ~600k w surowym formacie.

## Status i roadmapa

Toonic jest w fazie projektowania architektonicznego. Szczegółowy plan refaktoryzacji opisano w osobnym artykule. Kluczowe etapy to: fundament (FileHandler Protocol + FormatRegistry), handlery dokumentów, pluginy danych i konfiguracji, pluginy API i infrastruktury, oraz zunifikowany pipeline z CLI.

---

*Toonic to ewolucja code2logic rozwijana w ramach organizacji WronAI. Śledź postępy na [GitHub](https://github.com/wronai/code2logic).*
