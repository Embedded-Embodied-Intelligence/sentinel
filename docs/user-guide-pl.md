# Sentinel — przewodnik dla kierownika projektu

Sentinel pilnuje terminu i budżetu Twojego projektu. Po każdym raporcie statusu sprawdza,
czy termin jest zagrożony, i jeśli tak, proponuje konkretną zmianę: zastępstwo, osobę
tymczasową, przesunięcie terminów albo nową kolejność zadań. Zanim cokolwiek zaproponuje,
sprawdza każdą możliwość na setkach symulowanych scenariuszy przyszłości projektu. Zmiany,
które dotyczą ludzi, pieniędzy albo zakresu, zawsze czekają na Twoją decyzję.

Przewodnik jest dla osoby, która prowadzi projekt. Instalacja dla działu IT jest na
[końcu](#9-instalacja-dla-działu-it). Wersja angielska: [user-guide-en.md](user-guide-en.md).

**Spis treści:**
[1. Czym jest Sentinel](#1-czym-jest-sentinel) ·
[2. Pierwszy projekt](#2-pierwszy-projekt) ·
[3. Jak czytać przegląd](#3-jak-czytać-przegląd) ·
[4. Raport statusu](#4-raport-statusu) ·
[5. Rekomendacje i autonomia](#5-rekomendacje-i-autonomia) ·
[6. Symulator](#6-symulator) ·
[7. Prywatność](#7-prywatność) ·
[8. Najczęstsze pytania](#8-najczęstsze-pytania) ·
[9. Instalacja dla działu IT](#9-instalacja-dla-działu-it)

## 1. Czym jest Sentinel

Projekt rzadko idzie zgodnie z planem: ktoś choruje, zadanie okazuje się większe, pojawia się
nowa praca. Sentinel bierze Twój plan i to, co zgłaszasz w raportach statusu, i odgrywa
**200 możliwych przyszłości projektu** — z nieobecnościami i niespodziankami w takim tempie,
jakie wybierzesz przy zakładaniu projektu. Z tych scenariuszy wynika:

- **szansa na dotrzymanie terminu** (np. „39 %”: w 78 z 200 scenariuszy projekt kończy się w
  terminie),
- **najbardziej prawdopodobna data zakończenia** i **zły scenariusz** (jeden na dziesięć kończy
  się jeszcze później),
- **co zagraża terminowi** — zadania, od których termin zależy najczęściej,
- **rekomendacja**: najlepsza zmiana, sprawdzona na tych samych scenariuszach co prognoza.

Sentinel nie zgaduje i nie „czuje”: każda liczba na ekranie pochodzi z tych samych symulacji,
więc „bez zmian” na rekomendacji to dokładnie szansa z przeglądu. Sztuczna inteligencja (AI)
jest opcjonalna: może odczytać opis projektu albo wiadomość od zespołu i objaśnić decyzję
własnymi słowami, ale nigdy nie podejmuje decyzji.

![Strona startowa z listą projektów](ui/pl_start.png)

*Strona startowa: Twoje projekty z szansą na dotrzymanie terminu i liczbą decyzji, które na
Ciebie czekają.*

## 2. Pierwszy projekt

Kliknij **Nowy projekt**. Kreator ma trzy kroki; wszystko zapisuje się na bieżąco, więc możesz
przerwać i wrócić przyciskiem **Dokończ konfigurację** na stronie startowej.

### Krok 1: Podstawy

![Krok 1 kreatora: nazwa, daty, budżet, pewność szacunków](ui/pl_wizard_basics.png)

- **Nazwa projektu**, **Data rozpoczęcia** i **Termin** — ostatni dzień, do którego cała praca
  ma być gotowa. Bez terminu Sentinel pokaże prognozę dat, ale nie szansę ani rekomendacje.
- **Budżet (opcjonalnie)** w jednostkach kosztu: domyślnie jedna jednostka to jeden
  osobodzień (dzień pracy jednej osoby). Pozostaw puste, a Sentinel oszacuje budżet z zadań
  (z zapasem 10 %).
- **Jak pewne są szacunki czasu?** *Dość pewne*, *Typowe* albo *Zgrubne* — im mniej pewne, tym
  szerzej rozrzucone są czasy zadań w scenariuszach.
- **Jak burzliwy jest zespół?** *Spokojny*, *Typowy* albo *Burzliwy* — jak często zdarzają się
  nieobecności i niespodzianki.

### Krok 2: Zespół

Wpisz osoby z rolami (np. „Programista backendu”, „Tester”) albo kliknij **Wklej listę osób** i
wklej np. z arkusza po jednej osobie w wierszu: `Anna Nowak, Programista backendu`. Role to
dowolny tekst; wielkość liter i odstępy nie mają znaczenia („Tester” i „tester” to ta sama
rola). Kolejność ma znaczenie: przy
przydzielaniu pracy Sentinel wybiera najpierw osoby z góry listy.

### Krok 3: Zadania

Zadania możesz wprowadzić na trzy sposoby (zakładki u góry):

![Krok 3 kreatora: tabela zadań](ui/pl_wizard_tasks.png)

1. **Opisz projekt** — napisz własnymi słowami, co trzeba zrobić, kto i jak długo; AI
   odczyta zadania i zespół, a Ty je sprawdzisz przed użyciem (wymaga skonfigurowanego AI).
2. **Importuj arkusz** — pobierz **szablon zadań (CSV)**, wypełnij go w Excelu, LibreOffice albo
   Arkuszach Google i wgraj. Jeden wiersz to jedno zadanie:

   | id | name | duration_days | predecessors | optional | crew:Programista backendu | crew:Tester |
   | --- | --- | --- | --- | --- | --- | --- |
   | T1 | Projekt API płatności | 3 | | no | 1 | 0 |
   | T2 | Budowa API płatności | 5 | T1 | no | 2 | 0 |
   | T3 | Testy API płatności | 2 | T2 | no | 0 | 1 |

   `duration_days` to dni robocze, `predecessors` to identyfikatory zadań, które muszą się
   skończyć wcześniej (kilka oddziel spacją lub przecinkiem), `optional` = `tak` (albo `yes`)
   dla zadania, z którego można zrezygnować, a kolumny `crew:` mówią, ile osób z danej roli potrzeba (nazwy ról jak w kroku
   2). Błędy są wypisane z numerami wierszy; zapisz plik jako CSV (UTF-8).
3. **Dodaj ręcznie** — tabela: nazwa, dni robocze, liczba osób z każdej roli, po jakich
   zadaniach, czy opcjonalne. Problemy (np. pętla zależności, za mało osób w roli, termin
   wcześniejszy niż najkrótszy możliwy czas) są wypisane od razu, zwykłym językiem.

Kliknij **Utwórz plan**. Sentinel układa plan, który przy Twoim zespole kończy się możliwie
wcześnie, i otwiera przegląd projektu.

## 3. Jak czytać przegląd

![Przegląd projektu: szansa, daty i koszty](ui/pl_overview.png)

- **Szansa na dotrzymanie terminu** z oceną: *Na dobrej drodze* (80 % i więcej), *Zagrożony*
  (50–79 %), *Mało prawdopodobny* (poniżej 50 %). Strzałka pod spodem pokazuje zmianę od
  poprzedniego raportu statusu.
- **Termin**, **Najbardziej prawdopodobny koniec** (połowa scenariuszy kończy się wcześniej,
  połowa później) i **Zły scenariusz (1 na 10 później)**.
- **Wydano do tej pory** — np. „27 z 84 jednostek kosztu (osobodni)” — i **Oczekiwany koszt
  całkowity** z szansą na zmieszczenie się w budżecie. Jednostka kosztu to domyślnie
  osobodzień; jeśli w ustawieniach projektu podasz dzienne stawki (np. w złotych), koszty są w
  Twojej jednostce.
- **Czeka na Twoją decyzję** — rekomendacje, które wymagają zgody (rozdział 5).

Niżej:

![Co zagraża terminowi oraz plan i postęp](ui/pl_overview_threats.png)

- **Co zagraża terminowi**: zadania, które najczęściej decydują o terminie w scenariuszach,
  w których projekt się spóźnia, np. „Zadanie „API katalogu produktów” decyduje o terminie w 7
  na 10 scenariuszy z opóźnieniem”. Nie ma tu zadań, od których zależy cały plan (np. pierwsze
  i ostatnie zadanie), ani zadań już zakończonych. Jeśli żadne zadanie się nie wyróżnia,
  Sentinel pisze, że ryzyko rozkłada się na cały plan. Pod listą: kto jest nieobecny i które
  zadania nie zaczęły się zgodnie z planem.
- **Plan i postęp**: plan początkowy (szary), praca wykonana (zielona), w toku (niebieska, z
  obrysem pozostałej pracy), zaplanowana (jasnoniebieska) i nieobecności (paski), z dzisiejszym
  dniem i terminem. Ten sam wykres jest też dostępny jako tabela.

Przycisk **Zapytaj Sentinela** uruchamia nową analizę w dowolnej chwili (np. po zmianie
terminu w ustawieniach).

## 4. Raport statusu

Raport statusu mówi Sentinelowi, co się wydarzyło. Wystarczy raz w tygodniu (np. w piątek), a
w razie ważnej zmiany od razu. Kliknij **Raport statusu**.

![Raport statusu](ui/pl_checkin.png)

1. **Stan na koniec dnia** — dzień, którego dotyczy raport (zwykle dziś).
2. **Zadania w toku i najbliższe** — przy każdym: *Nierozpoczęte*, *W toku* z wykonaną częścią
   (suwak, w procentach) albo *Gotowe* z datą zakończenia. Opcjonalnie: kiedy zadanie się
   zaczęło i kto nad nim pracuje (domyślnie Sentinel przyjmuje plan i wolne osoby). Zadań, o
   których nic nie piszesz, nie trzeba ruszać.
3. **Ktoś jest nieobecny** — osoba, od kiedy i (jeśli wiadomo) do kiedy. **Tylko kiedy, nigdy
   dlaczego**: nie ma tu miejsca na powód nieobecności.
4. **Zadanie się wydłuża** — ile dodatkowych dni roboczych potrzebuje zadanie w toku.
5. **Nowe zadanie** — nazwa, dni robocze, po czym następuje i przed czym musi być gotowe.
6. Albo **napisz wiadomość** zwykłymi słowami („Ania choruje do środy, API zajmie jeszcze 3
   dni”) i kliknij **Odczytaj wiadomość**: AI wypisze, co znalazło, a Ty odznaczysz to, co się
   nie zgadza. Zapisują się tylko zaznaczone pozycje.

Kliknij **Zapisz raport**. Po kilku sekundach przegląd pokazuje nową szansę, a jeśli
potrzebna jest zmiana — rekomendację.

> **Dobra rada:** jeśli zastępca przejął zadanie, część jego czasu idzie na wdrożenie się.
> Sentinel liczy ten czas ostrożnie, dopóki zadanie trwa, więc szacunek pozostałej pracy
> poprawia się, gdy oznaczysz zadanie jako *Gotowe*.

## 5. Rekomendacje i autonomia

Po każdym raporcie Sentinel sprawdza możliwe zmiany i wybiera najlepszą: najpierw liczy się
szansa na dotrzymanie terminu, potem oczekiwane opóźnienie, budżet i to, jak mało zmienia się
plan. Rekomendacja pokazuje:

![Rekomendacja: działanie, efekt i powód](ui/pl_recommendation.png)

- **działanie** zwykłymi słowami, np. „Zastępstwo: Cezary Mazur przejmuje udział osoby
  nieobecnej (Bartosz Kowalski) w zadaniu „API katalogu produktów””,
- **efekt** w porównaniu z brakiem zmian: szansa („39 % → 55 %”), oczekiwany koniec, koszt
  („+2 jedn., +2 % budżetu”) i liczba zadań, których terminy się przesuwają,
- **dlaczego** potrzebna jest Twoja zgoda (*dotyczy ludzi*, *kosztuje*, *zmienia zakres* albo
  *zmienia plan bardziej, niż pozwala Twoje ustawienie*) i **dlaczego** wybrano tę zmianę,
- **porównane możliwości** — każda sprawdzona na tych samych 200 scenariuszach co prognoza na
  przeglądzie, więc „Bez zmian (zachowaj plan)” ma dokładnie szansę z przeglądu:

![Porównane możliwości](ui/pl_recommendation_options.png)

Na tych samych liczbach opiera się decyzja i oba wyjaśnienia. Gdy szanse są podobne, decyduje
kolejne kryterium i strona mówi to jednym zdaniem, np. „Podobna szansa (różnica w granicach
niepewności); wybrano wariant, który zmienia mniej terminów”; inna możliwość może wtedy mieć o
kilka punktów wyższą szansę.

Decydujesz przyciskami **Zatwierdź**, **Zdecyduj później** albo **Odrzuć**. Zatwierdzona zmiana
od razu trafia do planu (np. zastępca do zespołu zadania, osoba tymczasowa na wskazaną liczbę
dni). Oznaczenie **może poczekać** znaczy, że do realnego ryzyka zostało jeszcze kilka dni.
Rekomendacja „Bez zmian — plan wciąż jest najlepszy” to dobra wiadomość: żadna zmiana nie
pomaga bardziej niż obecny plan.

**Autonomia.** W **Ustawieniach** projektu wybierasz, co Sentinel może zrobić bez pytania:

![Ustawienia projektu: autonomia](ui/pl_settings.png)

| Ustawienie | Automatycznie | Czeka na Ciebie |
| --- | --- | --- |
| Tylko doradzaj | nic | każda zmiana |
| Może przesuwać terminy | przesunięcie terminów bez zmiany kolejności | reszta |
| Może zmieniać kolejność zadań (zalecane) | także nowa kolejność zadań | zastępstwa, osoby tymczasowe, rezygnacja z zadania |
| Może też dodawać osoby i zastępstwa | także zastępstwa i osoby tymczasowe | rezygnacja z zadania |

Zmiana zastosowana automatycznie jest widoczna na przeglądzie; nowe terminy albo nowa
kolejność zadań mają przycisk **Cofnij**, dopóki po nich nic się nie wydarzyło. W **Historii** widać każdy raport, rekomendację i decyzję.

## 6. Symulator

Symulator pozwala zobaczyć Sentinela w działaniu bez prawdziwego projektu: wybierz przykładowy
projekt (mały: 30 zadań, średni: 60 zadań), to, jak burzliwy jest zespół, i kto zarządza
projektem — **Sentinel** albo **Nikt nie reaguje**. Kliknij **Rozpocznij symulację**, a potem
symuluj po 1, 5 lub 10 dni albo **Do końca**.

![Symulator](ui/pl_simulator.png)

Na końcu tabela **Jak się skończyło** porównuje ten sam projekt z tymi samymi zdarzeniami
(nieobecności, wydłużone zadania, nowe zadania) prowadzony przez Sentinela i bez żadnej
reakcji: datę zakończenia, opóźnienie, koszt, zmiany planu, osoby tymczasowe i zastępstwa.
Oś czasu poniżej pokazuje, co się działo i co zrobił Sentinel.

![Porównanie w symulatorze](ui/pl_simulator_comparison.png)

Symulator używa ustawień aplikacji (np. zawsze można dodać co najmniej jedną osobę tymczasową
w każdej roli), a nie ustawień badań naukowych, więc jego wyniki mogą się od nich różnić. Jeden
przebieg to jeden możliwy los projektu; przypadek też ma znaczenie, więc warto spróbować kilku.

## 7. Prywatność

- Sentinel zapisuje tylko **dostępność** ludzi (od kiedy do kiedy ktoś jest nieobecny), **nigdy
  powodu** nieobecności — nie ma na niego pola (RODO, art. 9).
- Dane projektu są na serwerze, na którym działa Sentinel (Twój komputer albo serwer firmy).
  Bez AI nic go nie opuszcza.
- AI jest opcjonalne. **Model lokalny (Ollama)** działa na Waszym sprzęcie i nic nie wysyła na
  zewnątrz; modele w chmurze (Groq, OpenRouter) otrzymują tylko tekst, który odczytują.
  Odpowiedzi AI z prawdziwych projektów są zapamiętywane bez treści wiadomości.
- Wersja demonstracyjna w internecie: każdy odwiedzający dostaje własną piaskownicę, której nikt
  inny nie widzi; po 24 godzinach jest usuwana razem z projektami.

## 8. Najczęstsze pytania

**Skąd Sentinel wie, ile potrwają zadania?** Z Twoich szacunków i z tego, jak pewne one są
(krok 1). W każdym scenariuszu zadanie trwa trochę krócej albo dłużej, tak jak w życiu.

**Dlaczego szansa zmieniła się, choć nic nie zgłosiłem?** Nie zmienia się bez raportu albo
zmiany ustawień: te same dane dają zawsze te same liczby. Jeśli minął czas, a zadania się nie
zaczęły, zgłoś to w raporcie statusu.

**Czy muszę zatwierdzać rekomendacje?** Nie. Możesz je odrzucić albo zostawić na później.
Sentinel niczego nie zmienia w ludziach, pieniądzach ani zakresie bez Twojej zgody.

**Co oznacza „osobodzień”?** Dzień pracy jednej osoby. To domyślna jednostka kosztu; osoba
tymczasowa kosztuje półtora osobodnia dziennie. Własne stawki ustawisz w ustawieniach
projektu (**Dzienny koszt jednej osoby**).

**Czy mogę zmienić zespół albo zadania po pierwszym raporcie?** Nazwy, termin, budżet i
ustawienia — zawsze. Strukturę planu po pierwszym raporcie zmieniają raporty statusu (nowe
zadania, dłuższe zadania, nieobecności) i zatwierdzone rekomendacje.

**Jak pobrać dane?** W ustawieniach projektu: plan w CSV, cały projekt w JSON i szczegółowy
raport z wykresami.

**Czy AI może coś zmienić samo?** Nie. AI może tylko odczytać tekst (który i tak sprawdzasz)
i objaśnić decyzję; objaśnienie ma oznaczenie, czy zgadza się z danymi.

## 9. Instalacja dla działu IT

Szczegóły, kopie zapasowe i wersja demonstracyjna: [deploy.md](deploy.md) (po angielsku).

**Ważne:** aplikacja nie ma kont użytkowników — każdy, kto otworzy jej adres, widzi wszystkie
projekty. Udostępniaj ją tylko w sieci firmowej (VPN) albo za serwerem pośredniczącym z
logowaniem.

**Serwer firmowy (Docker):**

```bash
git clone https://github.com/Embedded-Embodied-Intelligence/sentinel.git && cd sentinel
docker compose up -d --build          # aplikacja na http://127.0.0.1:8000 serwera
docker compose ps                     # po ok. 30 s: (healthy)
```

Dane (projekty, ustawienia, klucz AI) są w wolumenie `sentinel-data`; aktualizacja:
`git pull && docker compose up -d --build`. Przykładowe projekty symulatora (jednorazowo):
`docker compose run --rm sentinel python /app/scripts/fetch_psplib.py --sets j30 j60 --root /data/psplib`.

**Laptop (bez Dockera):** zainstaluj [uv](https://docs.astral.sh/uv/), potem
`uv sync` i `uv run sentinel ui` → http://127.0.0.1:8000.

**AI — możliwości i koszty** (wybór na stronie **Ustawienia** aplikacji; klucz zostaje na
serwerze i nie jest więcej wyświetlany):

| Możliwość | Koszt | Czy dane wychodzą z firmy? |
| --- | --- | --- |
| Bez AI | bezpłatnie | nie; wszystko poza odczytem tekstu i objaśnieniami AI działa |
| Model lokalny (Ollama) | bezpłatnie; karta graficzna od 6 GB pamięci (albo wolniej na procesorze) | nie; `docker compose --profile ollama up -d` i `docker compose --profile ollama exec ollama ollama pull qwen2.5:7b` |
| Groq (chmura) | bezpłatny plan z dziennymi limitami | tak, do Groq (USA); klucz z console.groq.com |
| OpenRouter (chmura) | płatność za użycie (cennik na openrouter.ai) | tak, do OpenRouter i dostawcy modelu |
