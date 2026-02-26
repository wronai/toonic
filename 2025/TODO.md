jak za pomocą tego rozwiązania zastąpić makefile, wykorzystując komendy porpzez plik python i biblitoeke, ktora juz ma wbudowane podstaowe wszystkie funkcje, czyli np używam jako include biblitoeki, któ©a wspiera kolorwanie składni tych fragmentów toon w pliku, np przy załozeniu że korzystamy z biblitoeki dla pyhton ta bazowa biblioteka o np nazwie toonic

będe mógł wykorzystać ten zapis w formie komend w shell, np: toonic publish

wówczas mój plik pojedynczy z tą biblitoeką i konfiguracją w tym pojedynczym pliku z kodem

i decorators, oraz innymi formami annotaion będzie automatycznie publikowany do pypi

aby zminimalizować ilość kpotrzebnych danych jak np tworzenie pyproject.toml, requirements, itd



 python @toon/2.0

name: MyProject

version: 1.0.0

author: developer@example.com

license: MIT





Głównym założeniem, jest minimalizacja CICD, aby wiele automatycznych procesów było opisanych w annotation a procesy były realizowane niezalenize w sandbox docker poprzez toonic, w takiej sytuacji, nic nie zmieniamy w natywnym środowisku, tylko wykorzystujemy system CPU do generownaia w locie różnych artefaktów



Sama biblitoeka toonic powinna mieć temapltes, aby wiedzieć jak uruchomić typowe aplikacje, oraz LLM, poprzez litellm z lokalnym LLM, który będzie wspierał, gdy będzie potrzeba wygenerowania poprawnej wersji, jeśli templates nie bedą działać



toonic, ma być po części asystentem LLM, który będzie również wspierał kod usera, jeśli tam będą błędy, ale wsyzstko będzie robił w warswtei sandbox, aby nie zaśmiecać systemu plików,



znajdz rozwiażanie, aby działo się to szybko w tle