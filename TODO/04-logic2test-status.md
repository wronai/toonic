---
title: "Logic2Test — Generowanie Testów z Plików Logiki"
slug: logic2test-status
date: 2026-02-25
author: WronAI
categories: [projekty, logic2test, testing]
tags: [logic2test, testy, code2logic, LLM, automatyzacja]
excerpt: "Logic2Test generuje szkielety testów jednostkowych, integracyjnych i property-based bezpośrednio z plików logiki code2logic — bez konieczności czytania surowego kodu."
featured_image: logic2test-workflow.png
---

# Logic2Test — Generowanie Testów z Plików Logiki

## Problem: pisanie testów jest nudne, ale konieczne

Większość programistów zgadza się, że testy są ważne. Większość też przyzna, że pisanie ich jest jednym z najmniej wdzięcznych zadań. Zwłaszcza gdy projekt ma setki funkcji, a coverage wisi na 30%.

Logic2Test rozwiązuje ten problem, generując scaffolding testów bezpośrednio z plików specyfikacji code2logic. Model LLM nie czyta surowego kodu — czyta kompaktowy opis sygnatury, typów parametrów i intencji każdej funkcji, a na tej podstawie proponuje sensowne przypadki testowe.

## Jak to działa?

Przepływ jest prosty. Najpierw generujemy specyfikację projektu przez code2logic. Następnie logic2test parsuje tę specyfikację i dla każdej funkcji tworzy testy odpowiedniego typu.

```bash
# Krok 1: Analiza kodu
code2logic src/ -f yaml -o out/project.c2l.yaml

# Krok 2: Generowanie testów
python -m logic2test out/project.c2l.yaml -o tests/ --type all
```

W API Pythona:

```python
from logic2test import TestGenerator

generator = TestGenerator('out/project.c2l.yaml')
result = generator.generate_unit_tests('tests/')
print(f"Wygenerowano {result.tests_generated} testów")
```

## Typy generowanych testów

Logic2Test obsługuje trzy kategorie testów: unit tests (testy jednostkowe dla poszczególnych funkcji i metod), integration tests (testy integracyjne sprawdzające współpracę między modułami) oraz property-based tests (testy generatywne weryfikujące niezmienniki).

Każdy typ testów jest generowany na podstawie innego aspektu specyfikacji. Testy jednostkowe bazują na sygnaturach funkcji i ich intencjach. Testy integracyjne wykorzystują graf zależności między modułami. Testy property-based opierają się na typach parametrów i oczekiwanych zwracanych wartościach.

## Rola formatu TOON

W kontekście Toonic, logic2test staje się jeszcze potężniejszy. Specyfikacja w formacie TOON jest 5x mniejsza niż w JSON, co oznacza, że nawet mniejszy model LLM (8B–30B) poradzi sobie z generowaniem testów dla dużego projektu.

Docelowo logic2test będzie przyjmować nie tylko specyfikacje kodu, ale też specyfikacje schematów SQL (weryfikacja constraintów), API (testy endpointów z OpenAPI spec) i konfiguracji (testy poprawności konfiguracji).

## Status projektu

Logic2Test jest dostępny jako pakiet towarzyszący code2logic. Obsługuje generowanie testów w Pythonie (pytest) z planami rozszerzenia na JavaScript (Jest), TypeScript (Vitest) i Go (testing). Integracja z formatem TOON jest w fazie implementacji.

---

*Logic2Test jest częścią ekosystemu code2logic/Toonic. Dostępny na [GitHub](https://github.com/wronai/code2logic).*
