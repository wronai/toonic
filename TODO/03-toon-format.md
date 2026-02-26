---
title: "Format TOON — Token-Oriented Object Notation"
slug: toon-format-specification
date: 2026-02-25
author: WronAI
categories: [projekty, toonic, specyfikacja]
tags: [TOON, format, tokeny, LLM, kompresja, specyfikacja]
excerpt: "TOON to kompaktowy format zapisu struktury logicznej plików, zoptymalizowany pod kątem okna kontekstowego modeli LLM. Redukuje rozmiar 5-krotnie przy lepszej dokładności niż JSON."
featured_image: toon-format-comparison.png
---

# Format TOON — Token-Oriented Object Notation

## Problem: LLM nie potrzebują redundancji

Modele językowe opierają się na tokenach — każdy token kosztuje czas, pamięć i pieniądze. Standardowe formaty jak JSON czy YAML zostały zaprojektowane dla ludzi i maszyn epoki pre-LLM. Zawierają mnóstwo redundancji: powtarzane klucze, cudzysłowy, nawiasy, białe znaki — wszystko to, co LLM musi przetworzyć, ale co nie wnosi informacji.

TOON (Token-Oriented Object Notation) rozwiązuje ten problem. To format zapisu specyfikacji logicznych zoptymalizowany specjalnie pod kątem efektywnego wykorzystania okna kontekstowego LLM.

## Zasady projektowe

TOON opiera się na trzech zasadach: minimalizm tokenowy (każdy token musi nieść informację), czytelność maszynowa z zachowaniem ludzkiej przejrzystości, oraz deterministyczna struktura (parser nie potrzebuje kontekstu spoza pliku).

Format używa jednoliterowych kluczy (M=moduły, D=detale, i=importy, c=klasy, f=funkcje, m=metody), separatora przecinkowego zamiast nawiasów i minimalnego wcięcia dwuspacyjnego.

## Przykład: kod źródłowy w TOON

Nagłówek projektu zawiera kluczowe metryki w jednej linii:

```
# myproject | 42f 12500L | python:35/typescript:7
```

Oznacza to: projekt „myproject", 42 pliki, 12 500 linii, 35 plików Pythona i 7 TypeScript.

Moduły zapisane są kompaktowo z sygnaturami funkcji:

```
M[42]:
  core/auth.py,350
    f[3]: validate_token(token:str)->bool, create_session(user:User)->Session, hash_password(pwd:str)->str
  core/models.py,280
    c[2]: User(id,name,email), Session(token,user_id,expires)
```

## Przykład: schemat SQL w TOON

```
# schema.sql | postgresql | 6 tables | 3 views
T[6]:
  users     | id:bigserial PK, email:varchar(255) UNIQUE NN, created:timestamptz
  profiles  | user_id:bigint FK→users.id, bio:text, avatar_url:varchar
  posts     | id:bigserial PK, author_id FK→users.id, title:varchar(500) NN
V[3]: active_users, post_stats, user_activity
idx[4]: idx_posts_author, idx_posts_created, idx_comments_post, idx_tags_name
```

Cały schemat 6 tabel z relacjami, indeksami i widokami — w ~20 tokenach zamiast 500+ w surowym SQL.

## Przykład: dokument Markdown w TOON

```
# README.md | markdown | 1240w
D[3]:
  h1:Installation | Install via pip... | sub:2
  h2:Quick_Start | Run: code2logic... | 80w
  h2:Configuration | Set API key... | 120w
```

## Przykład: Kubernetes deployment w TOON

```
# deployment.yaml | kubernetes | Deployment
spec: replicas:3, image:myapp:v2.1, port:8080
resources: cpu:100m/500m, mem:128Mi/512Mi
env[3]: DB_HOST=postgres, DB_PORT=5432, LOG_LEVEL=info
```

## Porównanie formatów

Na próbie 20 plików projektu code2logic (156 modułów, 42 706 linii):

JSON zajmuje ~918 KB i ~235 000 tokenów. YAML to ~269 KB i ~69 000 tokenów. TOON — zaledwie ~170 KB i ~43 000 tokenów. LogicML jest jeszcze bardziej zwięzły (~245 tokenów/plik), ale kosztem pewnej utraty informacji.

W benchmarkach reprodukcji kodu TOON uzyskał 82.7% trafności — najlepszy wynik. JSON osiągnął 73.5%, YAML 71.1%. Brak szumu w formacie TOON sprawia, że model koncentruje się na istotnej informacji.

## Generator i parser

Code2Logic zawiera pełny generator TOON (`TOONGenerator` — 20 funkcji, ~600 linii) i parser (`TOONParser`). Generator obsługuje tryby: standard, compact, ultra-compact i function-logic. Parser odwraca proces — rekonstruuje strukturę danych z pliku TOON.

Format jest rozszerzalny — w ramach Toonic planowane są nowe kategorie: dokumenty (D), dane tabelaryczne (T), konfiguracja (C), API (A), infrastruktura (I), diagramy (G) i testy (X).

## Zastosowania praktyczne

TOON sprawdza się najlepiej jako format podawany do promptów LLM: refaktoryzacja projektu, code review architektoniczny, generowanie testów i dokumentacji, analiza bezpieczeństwa i cross-domain reasoning.

Praktyczna komenda z Claude Code:

```bash
code2logic ./ -f toon --compact --function-logic -o ./
claude --dangerously-skip-permissions -p "Zrób refaktoryzację projektu, wykorzystaj plik indeksu project.functions.toon"
```

---

*Format TOON jest częścią ekosystemu code2logic/Toonic. Specyfikacja schematu jest generowana automatycznie jako JSON Schema.*
