---
title: "Logic2Code — Generowanie Kodu ze Specyfikacji Logicznych"
slug: logic2code-status
date: 2026-02-25
author: WronAI
categories: [projekty, logic2code, generowanie-kodu]
tags: [logic2code, scaffolding, code2logic, LLM, reprodukcja]
excerpt: "Logic2Code odtwarza i scaffolduje kod źródłowy na podstawie specyfikacji logicznych code2logic — przydatne przy refaktoryzacji, migracji technologicznej i generowaniu szkieletów kodu."
featured_image: logic2code-pipeline.png
---

# Logic2Code — Generowanie Kodu ze Specyfikacji Logicznych

## Odwracamy pipeline

Code2Logic zamienia kod w specyfikację. Logic2Code odwraca ten proces — bierze specyfikację logiczną i generuje z niej kod źródłowy. To nie jest zwykły template engine — model LLM rozumie intencje każdej funkcji i generuje sensowną implementację.

## Zastosowania

Podstawowe scenariusze użycia logic2code to: scaffolding nowych modułów (generowanie szkieletów z pełnymi sygnaturami, typami i docstringami), refaktoryzacja (odtworzenie kodu z poprawioną strukturą na podstawie zmienionej specyfikacji), migracja technologiczna (np. przepisanie projektu z Django na FastAPI na podstawie specyfikacji modeli ORM) oraz generowanie stubów (implementacje placeholder dla mockowania i testowania).

## Workflow

```bash
# Pokaż co można wygenerować
python -m logic2code out/project.c2l.yaml --summary

# Generuj pełny kod
python -m logic2code out/project.c2l.yaml -o generated/

# Generuj tylko stuby
python -m logic2code out/project.c2l.yaml -o generated/ --stubs-only
```

W API Pythona:

```python
from logic2code import CodeGenerator

generator = CodeGenerator('out/project.c2l.yaml')
result = generator.generate('generated/')
print(f"Wygenerowano {result.files_generated} plików")
```

## Jakość reprodukcji

Benchmarki code2logic mierzą zdolność LLM do odtworzenia poprawnego strukturalnie i semantycznie kodu na bazie specyfikacji. Wyniki na próbie 20 plików pokazują, że format specyfikacji ma kluczowe znaczenie.

TOON osiąga 63.8% trafności w benchmarku projektowym — najlepszy wynik. Format ma też najwyższy wskaźnik „Runs OK" (60%), co oznacza, że wygenerowany kod częściej się kompiluje i uruchamia poprawnie.

Behavioral benchmark (testy równoważności behawioralnej) potwierdza 85.7% poprawności z 6/7 testów zaliczonych — model zachowuje logikę biznesową przy reprodukcji.

## Rola w ekosystemie Toonic

W ramach Toonic, logic2code zyskuje nowy wymiar. Zamiast odtwarzać tylko kod źródłowy, będzie potrafił generować kod z dowolnej specyfikacji TOON: schematy SQL → migracje, OpenAPI spec → klienty HTTP, Terraform spec → konfiguracje infrastruktury.

Kluczowa jest tu zasada „cross-format transpilacji": specyfikacja TOON jednego formatu może być użyta do wygenerowania pliku w zupełnie innym formacie. Na przykład: `api.toon → API_DOCS.md` lub `schema.toon → models.py`.

## Status projektu

Logic2Code jest funkcjonalny i dostępny jako pakiet towarzyszący code2logic. Obsługuje generację kodu w Pythonie z planami rozszerzenia na inne języki. System reprodukcji obsługuje cztery tryby: SpecReproducer (z plików YAML/JSON), CodeReproducer (plik → plik), ProjectReproducer (cały projekt) i ChunkedReproducer (dla modeli z małym kontekstem).

---

*Logic2Code jest częścią ekosystemu code2logic/Toonic. Dostępny na [GitHub](https://github.com/wronai/code2logic).*
