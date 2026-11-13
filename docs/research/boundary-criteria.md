# Boundary criteria and the process map (v3)

Where may AI work in a company and its management, where must a person stay? Sentinel answers
with six criteria instead of the single criterion "AI only where it saves time" (E27: in
management, automation cannot be neatly separated from augmentation). The same content, in
Polish for the interface's "Mapa granic", is `docs/research/boundary-map.json`; evidence ids
refer to `docs/research/evidence/registry.json`.

## Zones

| Zone | Meaning |
| --- | --- |
| AI samodzielnie (A) | AI does the work and its output is used without approving each item; a person can still look at it and correct it. |
| AI z człowiekiem (H) | AI prepares, a person checks and approves each output before it has any effect. |
| tylko człowiek (C) | The decision or the content belongs to a person; AI may supply facts computed by code (numbers, dates), but does not draft, rank or recommend. |

A process takes the **strictest zone of its six cells**: one criterion that keeps a person in
the loop is enough. The rule is deliberately conservative and simple to explain.

## Criteria

### 1. Odwracalność i stawka

Reversibility and stakes: whether an error can be undone cheaply before it does harm, and what it costs if it cannot.

- Test question: „Czy błąd AI w tym zadaniu da się cofnąć, zanim komuś zaszkodzi?”
- Evidence: E04, E07, E08, E09, E11, E12, E16, E23, E25, E26, E28, E30, E33, E40, E41, E44, E45, E50, E52

### 2. Weryfikowalność

Verifiability: whether a person or code can check the output cheaply and reliably before it is used.

- Test question: „Czy wynik AI można szybko sprawdzić (kodem albo okiem człowieka)?”
- Evidence: E03, E04, E06, E07, E11, E13, E14, E29, E30, E36, E37, E39, E47, E49

### 3. Praca językowa czy liczby i osąd

Language work or numbers and judgment: whether the task is language work inside the model's frontier (editing, summarising, text to data) or computation, new judgment or strategy outside it.

- Test question: „Czy to praca na tekście, czy liczenie, nowy osąd albo strategia?”
- Evidence: E01, E02, E05, E14, E15, E43, E44, E47, E48, E51

### 4. Wpływ na ludzi i pieniądze

Impact on people and money: whether the output affects the evaluation, work or money of particular people or of the company.

- Test question: „Czy wynik wpływa na ocenę, pracę lub pieniądze konkretnych osób?”
- Evidence: E08, E18, E19, E20, E21, E22, E32, E43, E46

### 5. Wartości, relacje i wyczucie („smak”)

Values, relations and taste: whether the decision depends on values, relations or tacit knowledge that no data can check. This criterion is normative.

- Test question: „Czy decyzja zależy od wartości, relacji lub wyczucia, których nie sprawdzi żadna liczba?”
- Evidence: E17, E22, E27, E31, E45

### 6. Wrażliwość danych

Data sensitivity: whether the task needs special-category or confidential data that should not reach a model or leave the company.

- Test question: „Czy zadanie wymaga danych wrażliwych lub poufnych?”
- Evidence: E19, E23, E24, E25, E26, E32, E33, E42

**Criterion 5 is normative.** The evidence for "taste" is theory (E17 prediction versus
judgment, E27 and E45 the automation–augmentation paradox, E31 Polanyi's paradox, which predates
language models that partly work around it by learning from examples) and one field study
whose quote is not yet verified (E22). No study shows that AI technically cannot weigh values or
relations; the criterion says where a person **should** stay, and the defence should say so.
The other criteria rest on studies with data (2, 3), on laws (4, 6) and on both (1).

## Process map

The twelve company processes of the survey (docs/research/v3-evidence-report.md, section D)
against the six criteria. Cell reasons and their evidence are in `boundary-map.json`.

| Process | 1 | 2 | 3 | 4 | 5 | 6 | Zone |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P01 Redakcja raportu napisanego przez człowieka | A | H | A | A | H | H | **AI z człowiekiem** |
| P02 Wersje raportu dla działów | A | H | A | H | H | H | **AI z człowiekiem** |
| P03 Streszczenie protokołu ze spotkania | A | H | A | H | A | H | **AI z człowiekiem** |
| P04 Zamiana wiadomości statusowych na dane o postępie | A | H | A | A | A | H | **AI z człowiekiem** |
| P05 Prognoza dotrzymania terminu | A | A | A | A | A | A | **AI samodzielnie** |
| P06 Wybór działania naprawczego w projekcie | H | H | H | H | H | A | **AI z człowiekiem** |
| P07 Streszczenie budżetu i odchyleń | A | H | A | A | A | H | **AI z człowiekiem** |
| P08 Zatwierdzenie przesunięcia budżetu lub wydatku | C | H | H | C | C | H | **tylko człowiek** |
| P09 Ocena wydajności pracownika | C | C | C | C | C | C | **tylko człowiek** |
| P10 Wybór osoby na zastępstwo | H | H | H | H | H | H | **AI z człowiekiem** |
| P11 Komunikat do zespołu o trudnej decyzji | C | C | H | C | C | H | **tylko człowiek** |
| P12 Decyzja strategiczna, np. wejście na nowy rynek | C | C | C | H | C | H | **tylko człowiek** |

## Why each process sits where it does

- **P01 Redakcja raportu napisanego przez człowieka** (AI z człowiekiem; deciding criteria 2, 5, 6; evidence E03, E27, E42, E43): Język to mocna strona modelu, ale redakcja może zmienić sens i fakty, więc każdą zmianę akceptuje autor. Raporty: śledzenie zmian i strażnik faktów (D14, D15).
- **P02 Wersje raportu dla działów** (AI z człowiekiem; deciding criteria 2, 4, 5, 6; evidence E03, E14, E27, E42, E43): Każda wersja to redakcja tekstu autora; dobór treści dla odbiorcy to osąd, więc wersje przegląda człowiek. Raporty: wersje dla odbiorców ze śledzeniem zmian (D16).
- **P03 Streszczenie protokołu ze spotkania** (AI z człowiekiem; deciding criteria 2, 4, 6; evidence E03, E20, E32, E39, E42): Streszczenie to praca językowa, ale model może zmyślić lub błędnie przypisać ustalenia, więc sprawdza je uczestnik. Raporty i Raport: szkic do potwierdzenia, nie gotowy protokół (D11, D14).
- **P04 Zamiana wiadomości statusowych na dane o postępie** (AI z człowiekiem; deciding criteria 2, 6; evidence E32, E47, E51): Model dobrze zamienia tekst na dane, ale nie zawsze dokładnie, więc każda pozycja jest kartą do potwierdzenia. Raport: karty „Do potwierdzenia”, domyślnie niezaznaczone (D11, D23).
- **P05 Prognoza dotrzymania terminu** (AI samodzielnie; deciding criteria 1, 2, 3, 4, 5, 6; evidence E14, E17, E18, E29, E32, E48, E49): Prognozę liczy symulacja, a nie model językowy; niczego nie zmienia i jest sprawdzalna, więc może działać sama. Pulpit: „N na 100” z symulacji Monte Carlo (D01, D13).
- **P06 Wybór działania naprawczego w projekcie** (AI z człowiekiem; deciding criteria 1, 2, 3, 4, 5; evidence E08, E11, E17, E18, E44, E45, E50, E51, E52): Symulacja ocenia możliwości i proponuje najlepszą, ale zmiana dotyczy ludzi i kompromisów, więc decyduje kierownik. Decyzja: propozycja z liczbami, Zatwierdź / Odrzuć / Popraw (D03, D05, D24).
- **P07 Streszczenie budżetu i odchyleń** (AI z człowiekiem; deciding criteria 2, 6; evidence E03, E14, E42): Liczby liczy kod, model tylko je opisuje; błąd w finansach jest kosztowny, więc streszczenie czyta człowiek. Finanse: podsumowanie bez prawa zatwierdzania (D17).
- **P08 Zatwierdzenie przesunięcia budżetu lub wydatku** (tylko człowiek; deciding criteria 1, 4, 5; evidence E08, E16, E17, E27, E40, E45): Wydanych pieniędzy nie da się cofnąć, a zatwierdzenie to odpowiedzialność osoby, więc AI może tylko przygotować liczby. Finanse: AI nie ma prawa zatwierdzać; decyzja i podpis należą do człowieka (D17, D19).
- **P09 Ocena wydajności pracownika** (tylko człowiek; deciding criteria 1, 2, 3, 4, 5, 6; evidence E02, E18, E19, E20, E21, E22, E32, E44, E46): Ocena ludzi przez AI to system wysokiego ryzyka, psuje miary i bezpieczeństwo zespołu, więc Sentinel celowo jej nie robi. Ludzie: funkcja celowo nieistniejąca (D09, D18).
- **P10 Wybór osoby na zastępstwo** (AI z człowiekiem; deciding criteria 1, 2, 3, 4, 5, 6; evidence E18, E20, E32, E41, E45, E50, E51): Symulacja pokazuje skutki zastępstwa według ról i dostępności, bez rankingu ludzi; kogo poprosić, wybiera kierownik. Decyzja: zastępstwo z Popraw (inna osoba), bez rankingu ludzi (D06, D18).
- **P11 Komunikat do zespołu o trudnej decyzji** (tylko człowiek; deciding criteria 1, 2, 4, 5; evidence E08, E22, E27, E31, E43, E45): Treść i ton trudnej wiadomości budują zaufanie i relacje, za które odpowiada kierownik; AI może najwyżej podać fakty z kodu. Poza Sentinelem: aplikacja podaje liczby, nie pisze takich komunikatów (D13, D20).
- **P12 Decyzja strategiczna, np. wejście na nowy rynek** (tylko człowiek; deciding criteria 1, 2, 3, 5; evidence E02, E06, E17, E29, E31, E44, E45): To nowy osąd o wysokiej stawce, którego nie da się sprawdzić przed faktem, więc należy do ludzi; AI może dostarczyć fakty. Poza Sentinelem: aplikacja wspiera projekty, nie strategię (D20).

The reasons are in Polish because the interface shows them. The map is Sentinel's position, not
a survey result: the survey (section D of the research report) asks respondents to place the
same twelve processes in the same three zones, so the two can be compared.
