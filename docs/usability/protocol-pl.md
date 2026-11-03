# Protokół testu użyteczności Sentinela (20 minut)

Moderowany test z głośnym myśleniem dla 3–5 uczestników, bez szkolenia (WP9c). Sprawdza, czy
osoba prowadząca projekty potrafi bez pomocy: założyć projekt z arkusza, odczytać prognozę,
zgłosić nieobecność, podjąć decyzję o rekomendacji i skorzystać z symulatora. Wyniki wpisuje
się do [szablonu wyników](results-template.md); punktem odniesienia jest skryptowy przebieg tych
samych zadań w wersji demonstracyjnej (`tests/test_ui_usability.py`,
[baseline-timing.json](baseline-timing.json), wersja 1.4.1).

**Wariant zdalny bez moderatora** (WP13): uczestnicy wykonują te same zadania w wersji
demonstracyjnej w internecie według pisemnej instrukcji i odsyłają kartę odpowiedzi (godziny
początku i końca zadań, odpowiedzi, łatwość 1–5, SUS); projekt nazywają swoim kodem, np. „P1
Aplikacja rezerwacji wizyt”. Kroki prowadzącego, eksport logu uczestnika i liczenie SUS:
[README](README.md).

## 1. Uczestnicy

- **3–5 osób**, które prowadzą projekty albo zespoły (kierownik projektu, lider zespołu,
  product owner, analityk). Pięć osób zwykle wystarcza, by znaleźć większość poważnych
  problemów (Nielsen i Landauer 1993).
- Nie znają Sentinela; nie pomagały go budować ani testować. Nie dostają szkolenia ani
  przewodnika przed testem.
- Każdy uczestnik osobno, na tym samym komputerze i w tych samych warunkach.

## 2. Przygotowanie (moderator, ok. 10 minut przed każdym uczestnikiem)

1. Laptop z przeglądarką w trybie pełnoekranowym, rozdzielczość co najmniej 1280 × 800.
2. **Czysty Sentinel dla każdego uczestnika** (osobny katalog danych, polski interfejs):
   ```bash
   uv run sentinel ui --data-dir ~/sentinel-test/P1      # P2, P3… dla kolejnych osób
   ```
   Otwórz http://127.0.0.1:8000 (strona startowa bez projektów). Dane przykładowych projektów
   symulatora muszą być pobrane (`uv run python scripts/fetch_psplib.py --sets j30 j60`).
   Model AI nie jest potrzebny.
3. Na pulpicie: plik [projekt-testowy.csv](projekt-testowy.csv) (zadania, wypełniony szablon
   CSV) i [zespol-testowy.txt](zespol-testowy.txt) (lista osób do wklejenia).
4. Wydrukowane karty zadań (rozdział 5, po jednej na kartkę), formularz SUS (rozdział 7),
   arkusz obserwacji ([szablon wyników](results-template.md)), stoper.
5. Nagrywanie ekranu i głosu — tylko za zgodą uczestnika (rozdział 3).

## 3. Nota o zgodzie (do odczytania i podpisania)

> Dziękuję za udział. Testujemy program, nie Ciebie: jeśli coś jest trudne, to wina programu i
> właśnie tego szukamy. Test trwa około 20 minut. Poproszę Cię o wykonanie pięciu zadań i o
> mówienie na głos, co myślisz. Na końcu wypełnisz krótką ankietę.
>
> Za Twoją zgodą nagram ekran i głos; nagranie posłuży tylko do analizy w tym projekcie
> studenckim, nie zostanie opublikowane i usunę je po opracowaniu wyników (najpóźniej do
> 31 stycznia 2027). W wynikach nie będzie Twojego imienia ani nazwiska — tylko kod (P1, P2…),
> rola zawodowa i lata doświadczenia. Dane w programie są fikcyjne. Możesz przerwać w każdej
> chwili, bez podawania powodu.
>
> ☐ Zgadzam się na udział w teście. ☐ Zgadzam się na nagrywanie ekranu i głosu.
>
> Data, podpis: ______________________

## 4. Przebieg i czas

| Czas | Etap |
| --- | --- |
| 0:00–0:02 | Powitanie, nota o zgodzie, pytania o rolę i doświadczenie (lata prowadzenia projektów) |
| 0:02–0:03 | Instrukcja głośnego myślenia (rozdział 6) |
| 0:03–0:16 | Pięć zadań (limity w rozdziale 5; razem do 13 minut) |
| 0:16–0:19 | Kwestionariusz SUS (rozdział 7) |
| 0:19–0:20 | Dwa pytania końcowe, podziękowanie |

Pomiar czasu zadania: od chwili, gdy uczestnik przeczyta kartę i powie „zaczynam”, do
osiągnięcia kryterium sukcesu albo do limitu czasu.

## 5. Zadania

Każdą kartę czyta uczestnik; moderator nie dodaje wyjaśnień. Dzisiejszą datą w scenariuszu
jest środa 4 listopada 2026, także gdy test odbywa się później (raport statusu ma wtedy datę z
przeszłości i zapisuje się bez pytań). Kalendarz projektu ma polskie święta (11 listopada jest
wolny). Wartości oczekiwane poniżej pochodzą ze skryptowego przebiegu wersji 1.4.1 w trybie
demonstracyjnym; są takie same w każdym dniu testu, poza datami symulatora (zadanie 5).

### Zadanie 1. Załóż projekt z arkusza (limit 6 minut)

> Prowadzisz projekt „Aplikacja rezerwacji wizyt”. Zaczyna się w poniedziałek 2 listopada 2026,
> a musi się skończyć do piątku 4 grudnia 2026. Zespół jest w pliku *zespol-testowy.txt*, a
> zadania w arkuszu *projekt-testowy.csv* na pulpicie. Załóż ten projekt w Sentinelu tak, aby
> powstał plan.

- **Sukces:** widać przegląd projektu z szansą na dotrzymanie terminu; projekt ma 5 osób i 7
  zadań.
- **Częściowy sukces:** projekt powstał, ale z pomocą moderatora albo z błędem poprawionym po
  podpowiedzi (np. inna data, brak osoby).
- **Obserwuj:** czy uczestnik znajduje *Nowy projekt* (w wersji demonstracyjnej obok projektu
  przykładowego), *Wklej listę osób* i kartę *Zaimportuj arkusz*; czy rozumie, co oznacza budżet
  i czy zagląda do *Więcej ustawień*; reakcję na wypisane problemy.
- **Punkt odniesienia (skrypt):** 9 kliknięć, 4 pola.

### Zadanie 2. Kiedy projekt najprawdopodobniej się skończy? (limit 1 minuta)

> Twój przełożony pyta, kiedy projekt najprawdopodobniej się skończy i czy zdążycie przed
> terminem. Co mu odpowiesz?

- **Sukces:** uczestnik podaje datę z pola *Najbardziej prawdopodobny koniec* i szansę na
  dotrzymanie terminu: **środa 2 grudnia** (2 dni robocze przed terminem) i **69 %** („Wymaga
  uwagi”), np. „najpewniej 2 grudnia, zdążymy na 69 %, ale w złym scenariuszu 11 grudnia”.
- **Częściowy sukces:** podaje tylko jedno z dwóch albo myli datę zakończenia z terminem.
- **Obserwuj:** jak rozumie „zły scenariusz (1 na 10 później)” i jednostki kosztu.
- **Punkt odniesienia:** 0 kliknięć (wszystko jest na przeglądzie).

### Zadanie 3. Zgłoś nieobecność (limit 3 minuty)

> Jest koniec dnia, środa 4 listopada. Warsztat z klientem zakończył się wczoraj (we wtorek
> 3 listopada). „Baza danych i API” jest w toku, zrobiono około 15 %. Bartosz Kowalski od jutra
> jest nieobecny, wraca w poniedziałek 16 listopada. Przekaż to Sentinelowi.

- **Sukces:** raport zapisany: warsztat gotowy 3 listopada, API w toku (10–20 %; 15 % zapisuje
  się jako 17 %, bo postęp liczy się w pełnych dniach: 1 z 6), nieobecność Bartosza od 5 do
  16 listopada.
- **Częściowy sukces:** zapisany z jednym błędem (np. data powrotu jako ostatni dzień
  nieobecności, brak postępu API).
- **Obserwuj:** czy szuka miejsca na powód nieobecności (nie ma go — to celowe); jak rozumie
  „Stan na koniec dnia” (formularz podpowiada dzisiejszą datę, a raport jest na 4 listopada) i
  „Powrót (jeśli wiadomo)”; czy zauważa licznik zmian na dole.
- **Punkt odniesienia:** 6 kliknięć, 5 pól.

### Zadanie 4. Zdecyduj o rekomendacji (limit 3 minuty)

> Sentinel coś proponuje. Sprawdź, co i dlaczego, i podejmij decyzję tak, jak w prawdziwym
> projekcie. Powiedz na głos, co zdecydowałeś i dlaczego.

- **Sukces:** uczestnik otwiera rekomendację *Zastępstwo: Celina Wiśniewska przejmuje udział
  osoby nieobecnej (Bartosz Kowalski) w zadaniu „Baza danych i API”* (oznaczoną „może
  poczekać”), własnymi słowami podaje jej efekt (szansa **39 % → 67 %**; najbardziej
  prawdopodobny koniec pon. 7 gru → śr. 2 gru; koszt 100 % → 102 % budżetu) i ją zatwierdza
  albo odrzuca z uzasadnieniem. Obie decyzje są sukcesem, jeśli uzasadnienie opiera się na tym,
  co pokazuje ekran.
- **Częściowy sukces:** decyzja bez zrozumienia efektu albo efekt bez decyzji.
- **Obserwuj:** czy rozumie „Wymaga Twojej zgody: dotyczy ludzi”, czy otwiera *Porównaj wszystkie
  możliwości* i czy widzi, że „Bez zmian” ma tę samą szansę co przegląd (39 %); jak odbiera
  zdanie o drugiej możliwości z szansą 68 % („podobna szansa … zmienia mniej terminów”).
- **Punkt odniesienia:** 2 kliknięcia.

### Zadanie 5. Symulator: kto poradził sobie lepiej? (limit 4 minuty)

> Chcesz zobaczyć, jak Sentinel radzi sobie z całym projektem. Uruchom symulację małego
> przykładowego projektu do samego końca i powiedz, kto poradził sobie lepiej: Sentinel czy
> „nikt nie reaguje” — i po czym to widać.

- **Sukces:** widoczna tabela *Jak się skończyło*; uczestnik poprawnie wskazuje, który
  przebieg skończył się wcześniej lub z mniejszym opóźnieniem, i podaje kryterium (data,
  opóźnienie, koszt): Sentinel kończy **10 dni roboczych wcześniej** niż „Nikt nie reaguje”
  (po terminie 8 zamiast 18 dni roboczych), za to drożej o 10 jedn. (103 % zamiast 102 %
  budżetu). Daty zależą od dnia testu (symulacja startuje dziś).
- **Częściowy sukces:** symulacja zakończona, ale wniosek niepełny albo oparty na jednej liczbie
  bez zrozumienia.
- **Obserwuj:** czy czeka na koniec symulacji (około minuty; w wersji demonstracyjnej
  symulacja biegnie odcinkami po 60 dni i strona sama ją kontynuuje); jak czyta oś czasu.
- **Punkt odniesienia:** 3 kliknięcia; około minuty (58 s w skrypcie).

## 6. Głośne myślenie i zasady moderatora

Instrukcja dla uczestnika (przed zadaniem 1):

> Proszę, mów na głos wszystko, co myślisz: czego szukasz, co Cię zaskakuje, czego się
> spodziewasz po kliknięciu. Nie ma złych odpowiedzi. Nie będę podpowiadać — jeśli utkniesz,
> powiedz to; jeśli skończysz, powiedz „gotowe”.

Zasady moderatora:

- Nie podpowiadaj i nie oceniaj („dobrze”, „prawie”). Gdy uczestnik milknie na dłużej niż
  10 sekund, zapytaj neutralnie: „Co teraz myślisz?”, „Czego szukasz?”.
- Na pytania o program odpowiadaj: „Jak myślisz?” albo „Co zrobiłbyś w pracy?”.
- Pomoc tylko wtedy, gdy uczestnik utknął na dłużej niż minutę albo prosi o nią: jedna
  podpowiedź, zapisana jako „z pomocą” (sukces najwyżej częściowy).
- Po przekroczeniu limitu przerwij zadanie, zanotuj „nieukończone” i przygotuj stan
  potrzebny do następnego zadania (moderator kończy krok za uczestnika).
- Notuj: czas, ścieżkę (gdzie klika), błędy (np. złe pole, cofnięcie), pomoc, cytaty.

## 7. Kwestionariusz SUS (System Usability Scale)

Standardowy kwestionariusz Brooke'a (1996), wypełniany zaraz po zadaniach, bez rozmowy o
programie. Skala: 1 — zdecydowanie się nie zgadzam, 2 — raczej się nie zgadzam, 3 — nie mam
zdania, 4 — raczej się zgadzam, 5 — zdecydowanie się zgadzam. Zaznacz jedną odpowiedź w każdym
wierszu; jeśli nie wiesz, zaznacz 3.

| # | Stwierdzenie | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Myślę, że chciałbym/chciałabym często korzystać z tego systemu. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 | System wydał mi się niepotrzebnie skomplikowany. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | System był łatwy w użyciu. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 | Myślę, że do korzystania z tego systemu potrzebowałbym/potrzebowałabym pomocy osoby technicznej. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 | Różne funkcje tego systemu były dobrze ze sobą połączone. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 | W systemie było zbyt wiele niespójności. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 | Wyobrażam sobie, że większość ludzi bardzo szybko nauczyłaby się korzystać z tego systemu. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 | System był bardzo niewygodny w użyciu. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 | Korzystając z systemu, czułem/czułam się bardzo pewnie. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | Musiałem/musiałam nauczyć się wielu rzeczy, zanim mogłem/mogłam zacząć korzystać z tego systemu. | ☐ | ☐ | ☐ | ☐ | ☐ |

**Wynik:** dla pytań nieparzystych (1, 3, 5, 7, 9) odpowiedź minus 1; dla parzystych (2, 4, 6, 8,
10) 5 minus odpowiedź; sumę (0–40) pomnóż przez 2,5 → wynik 0–100. Średni wynik w badaniach to
około 68 (Sauro i Lewis 2016); powyżej 80 to wynik bardzo dobry. Przy 3–5 osobach podawaj
średnią i zakres, bez wniosków statystycznych.

## 8. Pytania końcowe

1. Co było najtrudniejsze albo najbardziej zaskakujące?
2. Czy użył(a)byś Sentinela w swoim projekcie? Do czego tak, do czego nie?

## 9. Analiza

- **Skuteczność:** odsetek sukcesów (pełnych i częściowych) dla każdego zadania.
- **Czas:** mediana czasu zadania i jej stosunek do czasu skryptu (punkt odniesienia mierzy
  sam program, bez czytania i myślenia).
- **Problemy:** każdy zaobserwowany problem z liczbą osób, których dotyczył, i wagą
  (1 kosmetyczny, 2 drobny, 3 poważny, 4 blokujący; Nielsen 1994).
- **SUS:** średnia, minimum i maksimum.
- Wnioski i poprawki trafiają do raportu kursowego; nagrania usuwa się po opracowaniu.

**Źródła:** Brooke J. (1996) *SUS: a "quick and dirty" usability scale*; Nielsen J., Landauer
T. K. (1993) *A mathematical model of the finding of usability problems*; Nielsen J. (1994)
*Severity ratings for usability problems*; Ericsson K. A., Simon H. A. (1993) *Protocol
Analysis*; Sauro J., Lewis J. R. (2016) *Quantifying the User Experience*.
