# Raport z testu Sentinel (wersja 1.3.0), 3.11.2026

Uwaga do metodyki: część pól wpisałem skryptem, żeby zmieścić się w czasie (wiersze 3–11 tabeli zadań i statusy w raportach). Wiersze 1, 2 i 12, zespół, nieobecności, nowe zadania i wszystkie decyzje szły przez interfejs. Czasy w punkcie 7 są więc krótsze, niż zajęłoby to kierownikowi projektu.

## 1. Werdykt CEO

Dziś nie wdrożyłabym Sentinela u moich PM-ów jako narzędzia do decyzji. Mogłabym go puścić jako pilotaż na 2 projektach z zastrzeżeniem, że liczb nie raportujemy klientom. Przegląd i karty rekomendacji są najlepszym „jednym ekranem dla zarządu”, jaki widziałam w tej klasie narzędzi. W 2 minuty wiedziałam, co się pali i dlaczego. Zaufanie burzą liczby: tygodniowa nieobecność jednej osoby zbiła szansę z 56 % do 1 %, po zatwierdzeniu rekomendacji wychodzi inna szansa niż obiecana, a jako dzień końca pada 25 grudnia. Przekonałyby mnie spójne daty na wszystkich ekranach, polski kalendarz świąt i AI, które mówi, czego nie zrozumiało, zamiast po cichu pomijać połowę wiadomości.

## 2. Oceny 1–5

- **Pierwsze wrażenie: 4.** Czysty kreator w 3 krokach i dobre podpowiedzi. Wklejenie zespołu listą działa w ok. 4 s.
- **Czytelność przeglądu: 4.** Jedna liczba, trzy daty, budżet i „Co zagraża terminowi” konkretnymi zdaniami. Minus za nachodzące na siebie etykiety na osi.
- **Zaufanie do liczb: 2.** Duże skoki bez rozbicia na przyczyny, różne daty końca na różnych ekranach, obietnica ≠ wynik, święta ignorowane.
- **Zrozumiałość rekomendacji: 3.** Karta „przed → po” i porównanie opcji są świetne. Wyjaśnienie AI jest po angielsku i żargonem, a zdarza się rekomendacja „0 % → 0 %”.
- **Wysiłek raportu statusu: 2.** Datę z przyszłości trzeba potwierdzać po każdym błędzie, licznik zmian kłamie, a raport samym tekstem oznacza „zero postępu”.
- **Symulator jako narzędzie szkoleniowe: 4.** Wynik w jednym zdaniu nadaje się dla zarządu. Mylący jest wybór „Kto zarządza”, skoro i tak liczone są oba warianty.
- **Wygląd: 4.** Spokojny i spójny. Na 400 px nie ma poziomego przewijania, a tabela zamienia się w karty.
- **Szybkość: 4.** Plan powstaje w < 2 s, CSV w 113 ms. Wolniej działa tylko AI (6–8 s) i symulacja do końca (~40 s).

## 3. Błędy

### Poważne

**B1. PL/EN w kreatorze kasuje dane** (Nowy projekt → Podstawy)

- Kroki: wpisz nazwę, start i termin, rozwiń „Więcej ustawień”, kliknij EN.
- Oczekiwane: dane zostają.
- Faktycznie: formularz jest pusty, a data startu wraca do dzisiejszej.

**B2. Plan w eksporcie i na wykresie jest nieaktualny i łamie zależności** (Ustawienia → Eksport CSV; Przegląd → Plan i postęp)

- Kroki: 4 raporty, ostatni z nowym zadaniem „Baner cookies i polityka RODO” (musi być gotowe przed „Testy funkcjonalne”), potem eksport CSV.
- Oczekiwane: daty zgodne z prognozą (koniec 5 sty).
- Faktycznie:
  - „Migracja treści” ma plan 23–26 lis, czyli w przeszłości.
  - „Testy” mają 2–8 gru, a „RODO” 8–9 gru, więc kończy się już po testach.
  - „Uruchomienie” wypada 15 gru.

**B3. Szansa po zatwierdzeniu różni się od obiecanej** (Rekomendacja → Przegląd)

- Przykład 1: „Zastępstwo Paulina za Tomasza” obiecywało 1 % → 5 %, wyszło 14 %.
- Przykład 2: projekt przykładowy, „Cezary za Bartosza”: obiecane 39 % → 55 %, wyszło 46 %. Budżet poszedł ze 107 % na 113 %, choć obiecano +2 %.
- Oczekiwane: ten sam wynik albo wyjaśnienie różnicy.

**B4. Różne daty końca na jednym ekranie** (Przegląd i karta rekomendacji)

- Przegląd: „Najbardziej prawdopodobny koniec pon. 21 gru”. Karta: „Koniec wt. 22 gru → pon. 21 gru”.
- To samo przy 5 sty vs 6 sty i 30 gru vs 1 sty.
- Historia: „Utworzono plan: zakończenie wt. 15 gru”, a przegląd w tym samym momencie: 23 gru.

**B5. Kalendarz ignoruje polskie święta** (karta rekomendacji, raport 27 lis)

- Faktycznie: „Koniec pon. 28 gru → pt. 25 gru”.
- Oczekiwane: 24–26 grudnia to dni wolne.

**B6. AI w raporcie statusu po cichu pomija część wiadomości** (Raport statusu → „Przetwórz wiadomość”)

- „Marek jest na urlopie do środy, a testy potrwają 2 dni dłużej” → „AI nie znalazło w tej wiadomości nic do zgłoszenia”. W zespole nie ma Marka, a zadania testowe są dwa, ale nie padło żadne pytanie.
- „Filip … a testy integracyjne potrwają 2 dni dłużej” → zrozumiało tylko nieobecność Filipa (20–26 lis). Wydłużenie testów zniknęło bez śladu.
- Oczekiwane: lista „tego nie zrozumiałem” plus pytanie doprecyzowujące.

**B7. Wyjaśnienie AI jest po angielsku** (Rekomendacja → „Wyjaśnij innymi słowami (AI)”)

- Faktycznie: „Innymi słowy (AI, po angielsku)”, a w treści: „…because stability was the first component where they differed”.
- Oczekiwane: polski, bez żargonu.

**B8. Opis słowami źle zamienia się na zadania** (Zadania → „Opisz słowami”)

- „około tygodnia” → 7 dni roboczych zamiast 5.
- „możemy z nich zrezygnować” → zadanie nie dostało oznaczenia opcjonalnego. Podgląd nie ma nawet kolumny „Opcjonalne”.
- „testuje całość” zależy tylko od ERP i SMS, a pomija logowanie i płatności.
- Nazwy zadań to surowe fragmenty zdań, np. „dwóch programistów robi logowanie i uprawnienia”.

**B9. Raport samym tekstem oznacza zero postępu, bez ostrzeżenia** (Raport statusu)

- Kroki: wyślij tylko wiadomość, bez statusów zadań.
- Faktycznie: szansa spada z 46 % do 7 %.
- Oczekiwane: pytanie „Czy przez tydzień nic się nie posunęło?”.

### Drobne

**B10. Wstecz przeglądarki tuż po „Zapisz raport”.** Raport nie zapisuje się i nie ma żadnego ostrzeżenia.

**B11. Enter w polu „Rola” (Zespół)** czyści pole i nie dodaje roli.

**B12. Licznik zmian kłamie po przeładowaniu.** Po ostrzeżeniu o dacie albo błędzie walidacji stopka pokazuje „Bez zmian” lub „Zapisz raport (bez zmian)”, choć zmiany zostały zachowane.

**B13. Postęp zaokrąglany po cichu.** Wpisane 60 / 30 / 70 % zapisuje się jako 67 / 33 / 74 %.

**B14. Odłożona propozycja nie wróciła przy następnym raporcie.** Komunikat brzmiał: „Propozycja odłożona. Wrócimy do niej przy następnym raporcie”. Wróciła dopiero raport później.

**B15. Lista „Wybierz zadanie w toku” w sekcji „Zadania, które urosły”** zawiera też zadania nierozpoczęte i zakończone.

**B16. „Zakończone dnia” podpowiada datę startu projektu** (9 lis) zamiast daty z planu albo daty raportu.

**B17. Mylący komunikat o cyklu zależności.** Dostałem: „…nie może następować po „Testy funkcjonalne”, które samo zależy od „Testy funkcjonalne””.

**B18. Nazwy dłuższe niż 120 znaków są obcinane bez informacji.** Dotyczy nazwy projektu i nazwy zadania.

**B19. Kolejność projektów w panelu bocznym** zmienia się między ekranami.

**B20. Zaznaczenia w przewijanym okienku „Po zadaniach” (wiersz 12) przepadły po Esc.** Nie udało mi się tego pewnie odtworzyć.

### Kosmetyczne

**B21.** Komunikat „Podaj nazwę projektu” nie znika po wpisaniu nazwy.

**B22.** Na wykresie Gantta nachodzą na siebie etykiety „Najbardziej prawdopodobny koniec”, „Termin” i „Zły scenariusz”. Wykres w Historii nie ma osi Y.

**B23.** Stopka pokazuje raz „wersja 1.3.0”, a raz hash (np. „0837b8019f1e1ddc”) w Ustawieniach projektu.

**B24.** Symulator ucina tekst „…gdyby plan się już nie zmienia|”. Po „+10 dni” cały układ przeskakuje.

## 4. Tarcia UX

- **„Osoba jest nieobecna mniej więcej raz w roku”.** Nie wiadomo, na jak długo: dzień czy dwa tygodnie?
- **Budżet zaraz po utworzeniu projektu.** „0 z 60 jednostek kosztu … Oczekiwany koszt: > 99 % budżetu”: budżet z szacunku i od razu prawie przekroczony?
- **Tabela zadań:**
  - Nowy wiersz nie dostaje fokusu.
  - „Projekt nie ma jeszcze zadań” wisi nad tabelą w trakcie wpisywania.
  - Okienko „Osoby” przesunęło się, więc wpisałam DevOps zamiast frontendu.
- **Brak rekomendacji przy złej szansie.** „Nic nie czeka na Twoją decyzję” przy 38 % i przy 7 %.
- **Wykres planu.** Plan kończy się 15 gru, a „Okno prognozy” zaczyna się 24 gru. Luka nie jest nigdzie wyjaśniona.
- **Oś „dziś”** to w praktyce data ostatniego raportu, a nie dzisiejszy dzień.
- **Skok bez wyjaśnienia.** „spadek o 55 pkt proc.” po tygodniu, bez rozbicia, skąd się wziął. Do tego „spadek o 9 pkt” przy 14 % → 6 %.
- **Dziwne rekomendacje:**
  - Rekomendacja „0 % → 0 %” i tak czeka na decyzję.
  - „Dodatkowa osoba (tymczasowo): backend na 10 dni” daje wynik gorszy niż brak zmian.
  - Dwie opcje w porównaniu mają identyczną uciętą nazwę „Zastępstwo: Paulina Lis przejmuje…”.
- **Niezręczne zdanie:** „Następna w kolejności: … a następnie ułóż zadania na nowo, aby skończyć jak najszybciej (61 %)”.
- **Data z przyszłości.** „Ten raport ma datę … ponad tydzień od dziś” trzeba potwierdzać po każdym nieudanym zapisie.
- **Blokada edycji po starcie.** Nagłówek „Coś poszło nie tak” przy zwykłej regule: „Śledzenie postępu już się zaczęło, więc zespołu, zadań, ich szacunków… nie można już zmieniać”. Pomyłki w zależności nie da się poprawić.
- **„Zapytaj Sentinela”** brzmi jak czat, a tylko przelicza analizę.
- **Zmiana autonomii (3 → 4).** Widać tylko „Ustawienia zapisane”. Przegląd się nie zmienia, nie ma informacji, kiedy zmiana zadziała, a Historia pisze jedynie „Zmieniono dane projektu”.
- **Symulator.** Pytanie „Kto zarządza projektem?” jest zbędne, bo wynik i tak pokazuje obie kolumny.
- **CSV** ma nagłówki po angielsku przy polskim interfejsie.

## 5. Co zachwyciło

1. **Przegląd na jednym ekranie.** Szansa, trzy daty, budżet i „Co zagraża terminowi” konkretnymi zdaniami, np. „…miało się rozpocząć pon. 23 lis i jeszcze się nie rozpoczęło”.
2. **Karta rekomendacji.** Pokazuje przed → po, „Wymaga Twojej zgody: zmienia zakres”, porównanie 4–6 opcji i „Jak to policzyliśmy”. Odrzucenie wymaga potwierdzenia.
3. **Walidacje.** Termin przed startem, zadanie opcjonalne z zależnymi, cykle i daty z przyszłości są wyłapywane. Podwójny klik nigdy nie stworzył duplikatu.
4. **Symulator.** Zdanie „Z Sentinelem projekt skończył się 10 dni roboczych wcześniej niż bez reakcji, ale wciąż 8 dni roboczych po terminie” można wkleić prosto do materiałów dla zarządu.
5. **Wersja na telefon, raport HTML dla zespołu i prywatność nieobecności.** Przy nieobecnościach jest tylko „Tylko kiedy, nigdy dlaczego”.

## 6. Top 10 usprawnień (dla menedżera)

1. **Jedno źródło daty końca.** Ta sama data na przeglądzie, karcie i w historii, a obietnica rekomendacji zgodna z wynikiem po zatwierdzeniu. (M)
2. **Plan, Gantt i CSV przeliczane po każdym raporcie** zgodnie z prognozą i zależnościami. (M)
3. **Polski kalendarz świąt** i dni wolne firmy. (S)
4. **AI w raportach:**
   - lista „tego nie zrozumiałem”,
   - pytania o nieznane osoby i niejednoznaczne zadania,
   - wydłużenie zadań nierozpoczętych,
   - wyjaśnienia po polsku.

   (M)
5. **Rozbicie dużych zmian szansy na czynniki,** np. „−40 pkt: nieobecność Tomasza; −15 pkt: brak postępu w Migracji”. (M)
6. **Ostrzeżenie przy raporcie bez postępu** i przy raporcie samym tekstem. (S)
7. **Szybszy raport tygodniowy:**
   - domyślna data: poprzedni raport + 7 dni,
   - potwierdzenie daty raz na raport,
   - prawdziwy licznik zmian,
   - Enter, który nie kasuje danych.

   (S)
8. **Korekty planu po starcie** (zależności, szacunki) z wpisem w historii, zamiast blokady „Coś poszło nie tak”. (L)
9. **Opis słowami lepiej rozumiany:** tydzień = 5 dni roboczych, rozpoznawanie zadań opcjonalnych, krótkie nazwy zadań, kolumna „Opcjonalne” w podglądzie. Do tego zachowanie formularza przy przełączaniu PL/EN. (S/M)
10. **Autonomia:** podgląd, co się zmieni, i szczegółowy wpis w historii. Do tego zmiana nazwy „Zapytaj Sentinela” na „Przelicz teraz” albo prawdziwy czat. (S)

## 7. Czas

- **Przebieg A:** ok. 12 min (07:09–07:21). Człowiek wpisujący 12 zadań ręcznie potrzebowałby realnie 30–40 min.
- **Przebieg B:** ok. 3 min. Diagnoza „projekt w kłopocie i dlaczego” zajęła poniżej 1 min.
- **Przebieg C:** ok. 3 min.
- **Psucie:** ok. 4 min, rozłożone między przebiegi.
- **Razem:** ok. 19 min.

Wolne ekrany:

- „Odczytaj opis” (AI): 6–8 s, z komunikatem „Model lokalny może potrzebować kilku minut”.
- „Przetwórz wiadomość” (AI): ok. 8 s.
- „Wyjaśnij innymi słowami (AI)”: 5–8 s.
- Zapis raportu: 2–3 s, potem „Sentinel analizuje projekt…” jeszcze ok. 5 s.
- Symulator: +1 dzień ok. 1 s, +5 dni 6–8 s, +10 dni ok. 10 s, „Do końca” ok. 40 s, bez licznika dni w trakcie.
- Szybkie: utworzenie planu < 2 s, eksport CSV 113 ms, pozostałe ekrany < 1 s.

## Status po WP12 (wersja 1.4.0)

Legenda: **naprawione**, **zmienione** (inaczej, niż proponowano), **odrzucone** (z powodem).
Powtórzenie kroków B1–B19 w przeglądarce: `tests/test_ui_regression_e2e.py`.

### Błędy

- **B1 naprawione.** PL/EN w kreatorze zachowuje wpisane pola.
- **B2 naprawione.** Gantt, CSV i raport HTML pokazują bieżący plan: nic niegotowego w przeszłości, zależności (także nowych zadań) spełnione, sprawdzane `validate_residual`. Plan początkowy w osobnych kolumnach.
- **B3 naprawione.** Karta liczy opcję tak, jak zatwierdzenie ją stosuje (od razu, te same scenariusze), więc przegląd po zatwierdzeniu pokazuje dokładnie obiecaną szansę, daty i koszt. Przyczyny różnicy: rozpatrywanie zgody z jednodniowym opóźnieniem oraz powtórne losowanie scenariuszy, które wydłużało wdrożenie zastępcy razem z wcześniejszym wzrostem zadania. Gdy coś zmieni się po rekomendacji (termin, budżet, ustawienia), przegląd mówi to jednym zdaniem.
- **B4 naprawione.** Jedna funkcja dat. Karta pokazuje „najbardziej prawdopodobny koniec” z tych samych scenariuszy co przegląd. Data planu ma osobną etykietę „plan bez zakłóceń”, a Gantt jednym zdaniem wyjaśnia lukę do okna prognozy.
- **B5 naprawione.** Polskie święta (24–26 grudnia, Wielkanoc, Boże Ciało i pozostałe) oraz dni wolne firmy nie są dniami pracy. Projekty zapisane przed 1.4.0 zachowują swój kalendarz.
- **B6 naprawione.** Przegląd wiadomości pokazuje części, z których AI nic nie zrobiło. Pyta o osobę spoza zespołu i o zadanie pasujące do kilku. Nieobecność osoby, której wiadomość nie wymienia, jest odznaczona i opisana.
- **B7 naprawione.** Wyjaśnienie AI jest po polsku i prostymi słowami. Tekst z pojęciami wewnętrznymi zostaje poprawiony raz, a potem pominięty (ADR-0029).
- **B8 naprawione.** „Około tygodnia” to 5 dni roboczych. AI rozpoznaje zadania opcjonalne (w podglądzie jest kolumna „Opcjonalne”), nadaje krótkie nazwy z zachowanym zdaniem, a „testuje całość” następuje po wszystkich zadaniach programistycznych. Sprawdzone na obu modelach: `docs/qa/ai/wp12-*.json`.
- **B9 naprawione.** Raport bez postępu zadań w toku pyta: „Czy od <data> nic się nie posunęło?”.
- **B10 naprawione.** Opuszczenie strony w trakcie zapisu wywołuje ostrzeżenie przeglądarki.
- **B11 naprawione.** Enter w polu „Rola” dodaje rolę.
- **B12 naprawione.** Licznik zmian porównuje z zapisanym stanem, także po odrzuconym zapisie.
- **B13 naprawione.** Przy suwaku widać, co się zapisze: „60 % → zapisze się 67 %, 2 z 3 dni”.
- **B14 zmienione.** Komunikat mówi prawdę: propozycja czeka w „Czeka na Twoją decyzję” do następnego raportu, który liczy wszystko od nowa.
- **B15 naprawione.** Wzrost nierozpoczętego zadania jest nowym szacunkiem. Listy są pogrupowane i bez zadań gotowych.
- **B16 naprawione.** „Zakończone dnia” podąża za datą raportu.
- **B17 naprawione.** To samo zadanie jako „po” i „przed” ma własny, jasny komunikat.
- **B18 naprawione.** Przy limicie 120 znaków widać licznik.
- **B19 naprawione.** Kolejność projektów w panelu jest stała: najpierw czekające na decyzję, potem kolejność utworzenia.
- **B20 odrzucone: nie odtworzono.** Jedna próba w Playwright (wiersz 12, zaznaczenia, Esc): zaznaczenia zostają.
- **B21 naprawione.** Komunikat błędu pola znika po wpisaniu wartości.
- **B22 naprawione.** Etykiety na Gantcie nie nachodzą na siebie. Wykres w Historii ma oś Y.
- **B23 naprawione.** Stopka zawsze pokazuje wersję. Hash ustawień nie zasłania już numeru wersji.
- **B24 naprawione.** Tekst w symulatorze się zawija, a układ nie przeskakuje.

### Tarcia UX

- **Nieobecność „raz w roku”: naprawione.** Opis mówi „średnio przez 3 dni robocze”.
- **Budżet „> 99 %”: zmienione.** Udział kosztu pokazujemy bez zaokrąglania do „> 99 %”. W szczegółach jest zdanie, że budżet to szacunek z rezerwą 10 %, którą typowe wydłużenia w większości zużywają.
- **Nowy wiersz tabeli bez fokusu: naprawione.**
- **„Projekt nie ma jeszcze zadań” w trakcie wpisywania: naprawione.**
- **Okienko „Osoby” przesunięte: odłożone.** Raport nie podaje kroków ani rozmiaru okna, więc w WP12 tego nie badano. Sprawdzimy to w teście z użytkownikami.
- **Brak rekomendacji przy złej szansie: naprawione.** „Sentinel sprawdził N możliwości; żadna nie pomaga wystarczająco” z linkiem do porównania.
- **Luka między planem a oknem prognozy: naprawione.** Jedno zdanie pod Gantem.
- **Oś „dziś”: naprawione.** Linia brzmi „Stan na <data raportu>”, a osobna linia „Dziś” pojawia się, gdy to inny dzień.
- **Skok bez wyjaśnienia: naprawione.** Przy zmianie o co najmniej 5 pkt przegląd podaje do 3 przyczyn. Każda to szansa bez jednego zdarzenia, policzona na tych samych scenariuszach, z uwagą, że skutki się nie sumują.
- **Rekomendacja „0 % → 0 %”: naprawione.** Karta mówi, co się poprawia, np. oczekiwane opóźnienie.
- **Opcja gorsza niż „bez zmian”: naprawione.** W porównaniu ma etykietę „gorsze niż bez zmian”.
- **Identyczne ucięte nazwy: naprawione.** Skrót pokazuje początek i koniec nazwy.
- **„Następna w kolejności…”: naprawione.** Teraz: „Druga najlepsza możliwość, z szansą X: …”.
- **Data z przyszłości po każdym błędzie: naprawione.** Potwierdzenie raz na raport.
- **Blokada edycji po starcie: naprawione.** Spokojna informacja zamiast „Coś poszło nie tak”. Nierozpoczęte zadania można poprawić (szacunek, osoby, zależności, opcjonalność), a poprawka trafia do historii.
- **„Zapytaj Sentinela”: zmienione** na „Przelicz teraz”.
- **Zmiana autonomii: naprawione.** Komunikat mówi, co Sentinel od następnej analizy zrobi sam, a o co zapyta. Historia zapisuje stary i nowy poziom.
- **„Kto zarządza projektem?” w symulatorze: naprawione.** Pytanie usunięte, wynik nadal pokazuje oba warianty. Bieg „Do końca” liczy dni.
- **CSV po angielsku: naprawione.** Eksport i szablony w języku strony, import czyta oba języki.

### Top 10

- **#1, #2, #3, #5, #6: naprawione** (wyżej: B3/B4, B2, B5, skoki szansy, B9).
- **#4: naprawione** (B6, B7, B15).
- **#7: naprawione w części** (potwierdzenie daty raz, licznik, Enter). Domyślna data raportu zostaje „dziś”: zmiana jest odrzucona, bo raport opisuje stan na koniec dnia.
- **#8: naprawione** (korekty po starcie).
- **#9: naprawione** (B8, B1).
- **#10: naprawione** (autonomia, „Przelicz teraz”).
