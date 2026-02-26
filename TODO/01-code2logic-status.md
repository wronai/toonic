---
title: "Code2Logic — Status Projektu i Kierunki Rozwoju"
slug: code2logic-status
date: 2026-02-25
author: WronAI
categories: [projekty, code2logic, open-source]
tags: [code2logic, TOON, LLM, AST, refaktoryzacja]
excerpt: "Code2Logic to silnik analizy kodu źródłowego, który zamienia dowolny projekt w kompaktową reprezentację logiczną zoptymalizowaną dla modeli LLM. Oto aktualny stan projektu."
featured_image: code2logic-architecture.png
---

# Code2Logic — Status Projektu i Kierunki Rozwoju

## Czym jest Code2Logic?

Code2Logic to narzędzie open-source (Apache 2.0), które analizuje bazy kodu i generuje zwięzłe, przyjazne dla LLM reprezentacje logiczne. Zamiast podawać modelowi AI tysiące linii surowego kodu, Code2Logic tworzy specyfikację — mapę struktury, zależności i intencji — którą model może przetworzyć znacznie szybciej, taniej i z lepszą dokładnością.

Projekt obsługuje Pythona, JavaScript, TypeScript, Javę, Go, Rust i C# dzięki parserowi opartemu na Tree-sitter z inteligentnym fallbackiem na regex.

## Aktualne możliwości (v1.x)

Obecna wersja obejmuje pełny pipeline od kodu źródłowego do specyfikacji:

Analiza projektu realizowana jest przez moduł `ProjectAnalyzer`, który skanuje repozytorium i zbiera informacje o modułach, klasach, funkcjach, zależnościach i metrykach. Na bazie analizy AST (Tree-sitter) osiągamy 99% dokładności parsowania struktury kodu.

Grafy zależności budowane są przez moduł `DependencyAnalyzer` z użyciem NetworkX — algorytm PageRank identyfikuje najważniejsze moduły (huby), a detekcja cykli ostrzega o okrężnych zależnościach.

Generacja specyfikacji wspiera siedem formatów wyjściowych: YAML, TOON, JSON, Markdown, Compact, CSV i LogicML. Kluczowy jest format TOON — Token-Oriented Object Notation — który osiąga 5-krotną redukcję rozmiaru w porównaniu z JSON.

Reprodukcja kodu z plików logiki pozwala odtworzyć kod źródłowy na podstawie specyfikacji przy użyciu dowolnego modelu LLM (OpenRouter, Ollama, LiteLLM).

## Benchmarki

Najnowsze testy na próbie 20 plików z projektu pokazują wyraźne różnice między formatami:

W benchmarku projektowym TOON uzyskał 63.8% trafności reprodukcji — najlepszy wynik spośród wszystkich formatów. YAML osiągnął 62.4%, a JSON 64.4% w benchmarku tokenowym, lecz zużywa ponad 5 razy więcej tokenów niż TOON.

Rozmiar specyfikacji tego samego projektu (156 modułów, 42 706 linii) wynosi około 918 KB w JSON (~235 000 tokenów), natomiast tylko 170 KB w TOON (~43 000 tokenów). LogicML jest jeszcze bardziej kompaktowy — średnio 245 tokenów na plik przy zachowaniu 76%+ trafności.

## Ekosystem pakietów towarzyszących

Code2Logic działa jako centralne źródło prawdy dla dwóch pakietów towarzyszących:

**logic2test** generuje szkielety testów jednostkowych, integracyjnych i property-based bezpośrednio z plików logiki — bez konieczności czytania surowego kodu.

**logic2code** odtwarza i scaffolduje kod źródłowy na podstawie specyfikacji — przydatne przy refaktoryzacji, migracji technologicznej lub generowaniu stubów.

Pełny workflow wygląda tak: `code2logic src/ → spec.yaml → logic2test → testy` oraz `spec.yaml → logic2code → scaffolding`.

## Co dalej?

Projekt przechodzi transformację w kierunku **Toonic** — uniwersalnej platformy, w której format TOON staje się przenośnym nośnikiem danych dla wszystkiego: od dokumentów i konfiguracji, przez schematy baz danych, po archiwa całych projektów. Szczegóły w osobnym artykule.

---

*Code2Logic jest dostępny na [PyPI](https://pypi.org/project/code2logic/) i [GitHub](https://github.com/wronai/code2logic). Autor: Tom Sapletta.*
