# Wyniki testu użyteczności — szablon

Wypełnia moderator po każdym uczestniku ([protokół](protocol-pl.md)); w teście zdalnym bez
moderatora prowadzący, z karty odpowiedzi i logu uczestnika (`docs/usability/logs/P1.md`; jak:
[README](README.md)). Skopiuj plik jako `docs/usability/results-<rrrr-mm-dd>.md`; nie wpisuj imion
ani nazwisk, tylko kody P1–P5.

## Dane testu

| Pole | Wartość |
| --- | --- |
| Daty sesji | |
| Moderator | |
| Wersja Sentinela | 1.4.1 (wersja na dole menu po lewej; w teście zdalnym wersja demonstracyjna) |
| Komputer, przeglądarka, rozdzielczość | |
| Liczba uczestników | |
| Odstępstwa od protokołu | |

## Uczestnicy

| Kod | Rola | Lata prowadzenia projektów | Narzędzia używane na co dzień | Zgoda na nagranie |
| --- | --- | --- | --- | --- |
| P1 | | | | tak / nie |
| P2 | | | | |
| P3 | | | | |
| P4 | | | | |
| P5 | | | | |

## Zadania — wyniki uczestników

Wynik: **S** sukces, **C** częściowy sukces (także „z pomocą”), **N** nieukończone. Czas w
sekundach. Błędy: liczba błędnych kroków (złe pole, cofnięcie, ślepa uliczka).

| Zadanie | Uczestnik | Wynik | Czas [s] | Pomoc (ile razy) | Błędy | Uwagi i cytaty |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 1. Projekt z arkusza | P1 | | | | | |
| 1. Projekt z arkusza | P2 | | | | | |
| 1. Projekt z arkusza | P3 | | | | | |
| 1. Projekt z arkusza | P4 | | | | | |
| 1. Projekt z arkusza | P5 | | | | | |
| 2. Najbardziej prawdopodobny koniec | P1 | | | | | |
| 2. Najbardziej prawdopodobny koniec | P2 | | | | | |
| 2. Najbardziej prawdopodobny koniec | P3 | | | | | |
| 2. Najbardziej prawdopodobny koniec | P4 | | | | | |
| 2. Najbardziej prawdopodobny koniec | P5 | | | | | |
| 3. Nieobecność | P1 | | | | | |
| 3. Nieobecność | P2 | | | | | |
| 3. Nieobecność | P3 | | | | | |
| 3. Nieobecność | P4 | | | | | |
| 3. Nieobecność | P5 | | | | | |
| 4. Rekomendacja | P1 | | | | | decyzja: zatwierdź / odrzuć |
| 4. Rekomendacja | P2 | | | | | |
| 4. Rekomendacja | P3 | | | | | |
| 4. Rekomendacja | P4 | | | | | |
| 4. Rekomendacja | P5 | | | | | |
| 5. Symulator | P1 | | | | | kto lepszy i po czym |
| 5. Symulator | P2 | | | | | |
| 5. Symulator | P3 | | | | | |
| 5. Symulator | P4 | | | | | |
| 5. Symulator | P5 | | | | | |

## Podsumowanie zadań

Punkt odniesienia: skryptowy przebieg tych samych kroków bez czytania i myślenia
(`SENTINEL_TASK_TIMING=docs/usability/baseline-timing.json uv run pytest -q -m e2e -k usability`;
wartości z [baseline-timing.json](baseline-timing.json), skopiuj je przed testem).

| Zadanie | Sukces (S + C z n) | Mediana czasu [s] | Skrypt: kliknięcia / pola / s | Mediana / skrypt | Najczęstszy problem |
| --- | --- | ---: | --- | ---: | --- |
| 1. Projekt z arkusza | | | | | |
| 2. Najbardziej prawdopodobny koniec | | | | | |
| 3. Nieobecność | | | | | |
| 4. Rekomendacja | | | | | |
| 5. Symulator | | | | | |

## SUS

Wynik uczestnika: suma (pytania nieparzyste: odpowiedź − 1; parzyste: 5 − odpowiedź) × 2,5.

| Uczestnik | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Wynik (0–100) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P1 | | | | | | | | | | | |
| P2 | | | | | | | | | | | |
| P3 | | | | | | | | | | | |
| P4 | | | | | | | | | | | |
| P5 | | | | | | | | | | | |
| **Średnia (min–max)** | | | | | | | | | | | |

Odniesienie: średnia z wielu badań ≈ 68 (Sauro i Lewis 2016).

## Znalezione problemy

Waga: 1 kosmetyczny, 2 drobny, 3 poważny, 4 blokujący (Nielsen 1994).

| # | Problem (co się działo, gdzie) | Ekran | Ilu uczestników | Waga | Propozycja poprawki |
| --- | --- | --- | ---: | ---: | --- |
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

## Odpowiedzi na pytania końcowe

| Uczestnik | Najtrudniejsze / zaskakujące | Czy użył(a)by w swoim projekcie? |
| --- | --- | --- |
| P1 | | |
| P2 | | |
| P3 | | |
| P4 | | |
| P5 | | |

## Wnioski

- Co działa bez szkolenia:
- Co trzeba poprawić przed oddaniem (waga 3–4):
- Co można poprawić później (waga 1–2):
- Ograniczenia testu (liczba osób, fikcyjny projekt, warunki laboratoryjne):
