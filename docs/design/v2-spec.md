# Sentinel v2 — UX specification

Status: agreed with the owner on 2026-11-07 (design workshop). Binding for WP15 and WP16.
The interface text is Polish (English as the second language); this specification is in English
except for the interface labels, which are quoted exactly as they must appear.

## 0. Scope and coexistence

- v2 is a new interface on the **same engine and services** (forecast, threats, causes, options,
  check-ins, messages, voice, event log). Nothing in the research core changes.
- v2 lives under **`/v2`**; the current interface stays at `/` untouched until the owner switches.
  Both work in normal and demo mode. The start page of v1 gets one link "Nowy wygląd (v2)".
- Platform: **Chrome on a laptop**. Layouts are designed and checked at **1440×900 and
  1280×800**; nothing is required below 1180 px wide (no tablet or phone layouts; the page must
  not break, a horizontal scroll is acceptable below 1180 px).
- Stack unchanged (ADR-0025): FastAPI, Jinja templates, HTMX, hand-written CSS, inline SVG, system
  fonts, no CDN, **no new runtime dependency**. v2 may have its own stylesheet
  (`sentinel-v2.css`) and script (`sentinel-v2.js`).

## 1. Users

- **Primary:** a project manager or team lead with 2–5 projects (a company PM, a university
  lecturer running a project with students). Looks at the app daily (often in the evening, for
  under a minute) and reports once a week.
- **Design target:** a **novice** — about 18, new to business ("akcelerator": the app guides a
  beginner through running a project). Every input has an example inside it, a hint under it and
  a sensible default; an expert is never slowed down (novice-to-expert design).

## 2. Design principles (with sources)

1. **One screen, readable at a glance; details one click away** (Few 2006, *Information Dashboard
   Design*; progressive disclosure).
2. **Status by colour, size and position first, text confirms** (pre-attentive processing: Ware
   2012; Healey & Enns 2012).
3. **About four blocks above the fold** (working memory ≈ 4 items: Cowan 2001; cognitive load:
   Sweller 1988).
4. **Few, large choices** (Hick 1952; Fitts 1954): one primary action per screen; decision buttons
   large; approve is green with ✓, reject is red with ✕.
5. **Chance as a natural frequency** — "39 na 100", with a 10×10 dot grid — not a percentage
   (Gigerenzer & Hoffrage 1995; icon arrays: Galesic et al. 2009; Spiegelhalter et al. 2011).
6. **Language of consequences**, honest and two-sided: days late, work-days of budget, chance
   before → after (prospect theory: Kahneman & Tversky 1979; framing: Tversky & Kahneman 1981).
   Numbers are always true and both gains and costs are shown.
7. **Human in the loop; the manager can correct, not only accept** (trust calibration: Lee & See
   2004; Parasuraman & Riley 1997; algorithm aversion: Dietvorst et al. 2015, 2018; levels of
   automation per function: Parasuraman, Sheridan & Wickens 2000; out-of-the-loop: Endsley & Kiris
   1995; automation bias: Mosier & Skitka 1996; EU AI Act 2024/1689 Art. 14).
8. **Contrastive explanations**: why this and not the alternative, in two sentences (Miller 2019).
9. **Interrupt only on material change** (cost of interruption: Mark et al. 2008).
10. **Colour never alone** — colour + icon + word (WCAG 2.2 SC 1.4.1); calm rounded cards, sharp
    clear warnings (Bar & Neta 2006). Text contrast ≥ 4.5:1 (WCAG AA).

Plain language: ISO 24495-1:2023. **Headings are nouns, buttons are verbs** (Apple HIG, Microsoft
Writing Style Guide). Address the user as "ty"; people by first name.

What the app deliberately does **not** do (record as a design decision): no telemetry from other
tools; **no per-person performance metrics** (Goodhart; Edmondson 1999 psychological safety;
Deming 1986; AI Act Annex III point 4 lists evaluating workers' performance as high-risk) — the
team view shows **workload** ("3 zadania naraz w przyszłym tygodniu"), never performance; **no
question about how often a person is absent** (unknowable, health-adjacent, GDPR Art. 9): one
team-wide default from public Polish absence statistics (source and value documented).

## 3. Decision model (human in the loop)

- Sentinel **collects, analyses and prepares** a decision with its justification. **Every change
  to the project — including a pure re-ordering of the plan — happens only after the manager
  approves it.** In the engine this is the permission gate with every action requiring approval
  (the strictest level); the research configurations are unchanged. The autonomy setting
  disappears from the interface; in its place a fixed block "Jak Sentinel podejmuje decyzje":
  "Sentinel zbiera informacje, analizuje projekt i przygotowuje decyzje. Każdą zmianę zatwierdzasz
  Ty."
- **Lifecycle** of a proposal, all of it kept in the archive (Dziennik; AI Act Art. 12):
  `oczekuje` → `zatwierdzona` | `odrzucona` (with reason) | `odłożona` (back to `oczekuje` on the
  next visit after a day) | `poprawiona` (the manager changed its parameter; a new evaluation) |
  `wygasła` (its validity date passed) | `zastąpiona` (a newer report recomputed it). Each change
  records time, actor ("Ty" / "Sentinel") and, for decisions, the brief as it was at that moment.
- **Validity date ("ważna do")**: the last working day on which applying the action still
  improves the chance by at least the materiality threshold, found by evaluating the chosen
  action applied 0, 1, 2, … working days later on the same worlds (stop at the first day it no
  longer helps; at most 10 days); computed in the background job after the recommendation.
- **Cost of delay**: the chance lost per day of waiting, from the same evaluation
  ("Każdy dzień czekania to ok. −2 na 100"); shown when ≥ 1 na 100.
- **Never executed by silence.** Reminders only: the decision stays at the top of Start and the
  project's Pulpit; one day before its validity date it is marked "wygasa jutro" in red; a new
  report recomputes it (the old one becomes `zastąpiona`).
- **Correction ("Popraw")** changes the one parameter the model can evaluate: substitution →
  another eligible person; temporary person → role and number (and days if the model supports
  them); descoping → another optional task; plan re-ordering → no correction. After a change the
  effects are recomputed and the decision becomes `poprawiona`.
- **Rejection reasons** (one click, then confirm): "Za drogo" · "Osoba niedostępna" · "Brak
  środków" · "Inny powód" (opens the text box with the microphone). The reason goes to the
  archive.

## 4. Numbers and states

- Chance: integer **"N na 100"** (rounded from the forecast's worlds), with a 10×10 dot grid.
  "Skąd ta liczba?" expands: "Sentinel rozegrał ten projekt {W} razy, za każdym razem z innymi
  losowymi zdarzeniami (choroby, zadania krótsze lub dłuższe niż w planie), zgodnie z tym, co
  wiemy z raportów. W {K} z nich — czyli {N} na 100 — projekt skończył się przed terminem."
- **States** (colour + icon + word):

  | State | Chance | Colour | Verdict sentence |
  | --- | --- | --- | --- |
  | "Na dobrej drodze" | ≥ 80 | green | "Zdążymy z zapasem ok. {d} dni roboczych." |
  | "Zagrożony" | 50–79 | amber | "Raczej zdążymy, ale zapas jest mały (ok. {d} dni roboczych)." |
  | "Nie zdążymy bez zmian" | < 50 | red | "Spóźnimy się o ok. {d} dni roboczych." |

  `{d}` = working days between the most likely finish and the deadline. Second line: "Główna
  przyczyna: {first cause of the last change, or first main risk}." (P80 is a common confidence
  level for schedule reserves; below 50 the most likely finish is after the deadline, so the red
  state always agrees with "Spóźnimy się".)
- Budget in **"dni pracy"** (work-days): "wydane {a} z {b} dni pracy · na koniec ok. {c} ({±p} %)".
- **"Zapas czasu"** chart (buffer-consumption / fever chart; Goldratt 1997, Leach 2014):
  x = share of the project's work done (0–100 %), y = share of the time reserve used (0–100 %+),
  where reserve = deadline − end of the baseline plan, used = most likely finish − baseline end
  (clamped at 0). Three zones (green / amber / red by equal thirds of the diagonal band), one dot
  per report joined by a line, the latest dot larger. If the baseline had no reserve (≤ 0 days),
  show "Plan od początku nie miał zapasu czasu" instead of the chart. Subtitle: "Ile zapasu
  zjedliśmy w stosunku do postępu prac".

## 5. Visual system

- **Light theme by default**; dark and system as options ("Wygląd": "Jasny" · "Ciemny" ·
  "Systemowy"), remembered per browser (cookie so the server renders it without a flash).
- Character: calm, trustworthy, premium. White content surfaces; one accent colour (keep the
  current accent if it passes contrast); neutral greys; status colours reserved for states
  (green #15803d, amber #b45309, red #b91c1c on white, or close values that pass AA).
- **Glass** only on the navigation chrome (sidebar or top bar: subtle translucency and blur), never
  behind text content or numbers; switched off under `prefers-reduced-transparency` and in any
  case where text contrast would fall below AA. If in doubt, solid white.
- Typography: system stack (`-apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif`),
  **body 17 px**, line-height 1.5; headings 600–700; hero numbers 44–56 px bold with tabular
  figures; never below 14 px.
- 8-px spacing grid; cards radius 16 px, soft shadow; buttons ≥ 44 px high; one primary button per
  screen. Approve: filled green with ✓; reject: red with ✕ (filled or strong outline); secondary
  actions as quiet buttons or links. Visible focus ring everywhere.
- Icons: inline SVG drawn for the project. No brand assets.

## 6. Microcopy

Rules: ISO 24495-1; headings nouns, buttons verbs; "ty"; consequences first; two levels — one
sentence on top, the full explanation under "Szczegóły" (nothing technical is cut, only placed
one level down). No internal terms (run the existing internal-term checker on v2 too).

| Element | Label (PL) | EN |
| --- | --- | --- |
| Start heading | "Projekty" | "Projects" |
| Start list | "Decyzje do podjęcia" | "Decisions to make" |
| Start feed | "Ostatnie zdarzenia" | "Recent events" |
| Project tabs | "Pulpit" · "Raport" · "Decyzje" · "Dziennik" · "Plan" · "Ustawienia projektu" | "Overview" · "Report" · "Decisions" · "Log" · "Plan" · "Project settings" |
| Chance block | "Szansa na termin" | "Chance of the deadline" |
| Chance help | "Skąd ta liczba?" | "Where does this number come from?" |
| End block | "Koniec projektu" ("najpewniej", "w złym razie") | "Project end" ("most likely", "in a bad case") |
| Budget block | "Budżet" | "Budget" |
| Pending decision | "Decyzja do podjęcia" · "ważna do {data}" | "Decision to make" · "valid until {date}" |
| Chart | "Zapas czasu" | "Time reserve" |
| Upcoming | "Najbliższe 7 dni" | "Next 7 days" |
| Causes | "Przyczyny zmiany" | "Causes of the change" |
| Risks | "Główne ryzyka" | "Main risks" |
| Report step 1 | "Zdarzenia od ostatniego raportu" | "Events since the last report" |
| Report quick button | "Postęp zgodny z planem" | "Progress as planned" |
| Report step 2 | "Do potwierdzenia" — "Zaznacz zmiany, które się zgadzają." | "To confirm" |
| Unparsed | "Nierozpoznane fragmenty" | "Unrecognised parts" |
| Report step 3 | "Wpływ na projekt" | "Effect on the project" |
| Report save | "Zapisz raport" | "Save report" |
| Form fallback | "Wypełnij formularz" | "Fill in the form" |
| Decision buttons | "Zatwierdź" · "Odrzuć" · "Popraw" · "Odłóż decyzję" | "Approve" · "Reject" · "Adjust" · "Postpone" |
| Decision sections | "Skutek" · "Uzasadnienie" · "Kogo dotyczy" · "Koszt zwłoki" · "Szczegóły" | "Effect" · "Reasoning" · "Who is affected" · "Cost of delay" · "Details" |
| Reject reasons | "Za drogo" · "Osoba niedostępna" · "Brak środków" · "Inny powód" · "Potwierdź odrzucenie" | "Too expensive" · "Person unavailable" · "No budget" · "Other reason" · "Confirm rejection" |
| People notice | "Dotyczy ludzi, dlatego wymaga Twojej zgody." | "It affects people, so it needs your approval." |
| Postpone note | "Przypomnę przy następnej wizycie. Decyzja ważna do {data}." | — |
| Lab | "Laboratorium" · "Co jeśli?" · "Symulator" · "Mało zakłóceń" · "Dużo zakłóceń" · "Dodaj do raportu" | "Lab" · "What if?" · "Simulator" · "Few disruptions" · "Many disruptions" · "Add to report" |
| Settings | "Wygląd" · "Język" · "Model AI" ("Chmura (zalecany)" · "Lokalny") · "Kalendarz" · "Jak Sentinel podejmuje decyzje" · "Usuń projekt" | — |

Adjust the remaining labels to the same rules; record each in the glossary file used by the
translation tests.

## 7. Navigation

- Left sidebar (glass allowed): **Start** · **Projekty** · **Dziennik** · **Laboratorium** ·
  **Ustawienia**; at the bottom the language and theme switch and the version.
- Inside a project, tabs: **Pulpit** · **Raport** · **Decyzje** · **Dziennik** · **Plan** ·
  **Ustawienia projektu**. The header of every project page: name, "stan na {data, godzina}", and
  the primary action "🎤 Raport" (on Pulpit).
- **Live banner** while the app is open (HTMX poll every 20 s of new events since the last seen):
  a new decision; a project changed state; the chance changed by ≥ 10 na 100. Text: "{Projekt}:
  szansa spadła z 92 do 39 na 100 · Zobacz". No browser notifications (future feature).

## 8. Screens

Wireframes are indicative; the rules are binding.

### 8.1 Start (WP15)
```
Projekty · pt 13 lis                                         [ + Nowy projekt ]
DECYZJE DO PODJĘCIA (2)                          posortowane wg daty ważności
 Nowa odsłona sklepu · Celina zamiast Bartosza · +28 na 100 · ważna do czw 12 lis
 Aplikacja rezerwacji · Rezygnacja z SMS     · +9 na 100  · ważna do pon 16 lis
PROJEKTY   [● Nie zdążymy bez zmian | Nowa odsłona sklepu | Spóźnimy się o ok. 2 dni | 39 na 100 · 1 decyzja]
           [● Na dobrej drodze | Aplikacja rezerwacji | Zapas ok. 6 dni | 81 na 100]   [+ Nowy projekt]
OSTATNIE ZDARZENIA                                                Cały dziennik ›
 18:42 Ty        Odrzucono: osoba tymczasowa (za drogo)
 18:40 Sentinel  Nowa propozycja: Celina zamiast Bartosza
```
- All pending decisions of all projects, **sorted by validity date** (a hard date, never by an AI
  judgement), each with its effect. Empty: "Brak decyzji do podjęcia".
- Tiles: state (colour + icon + word), name, verdict sentence, "N na 100", pending count.
- First visit (no projects): "Zacznij od pierwszego projektu" with three large cards: "Zaimportuj
  arkusz" · "Opisz projekt głosem" · "Otwórz projekt przykładowy".

### 8.2 Pulpit (WP15)
Above the fold at 1280×800: (1) verdict, (2) three numbers, (3) the pending decision.
```
Nowa odsłona sklepu            stan na pt 13 lis, 18:40               [🎤 Raport]
● NIE ZDĄŻYMY BEZ ZMIAN
Spóźnimy się o ok. 2 dni robocze.
Główna przyczyna: Bartosz nieobecny do pon 16 lis.
| SZANSA NA TERMIN        | KONIEC PROJEKTU           | BUDŻET                         |
| 39 na 100  [dot grid]   | najpewniej wt 22 gru      | wydane 27 z 84 dni pracy       |
| Skąd ta liczba? ›       | termin pt 18 gru          | na koniec ok. 92 (+9 %)        |
|                         | w złym razie pt 5 sty     |                                |
DECYZJA DO PODJĘCIA · ważna do czw 12 lis
Celina przejmuje zadania Bartosza
Szansa 39 → 67 na 100 · Koniec 22 gru → 18 gru · Budżet +2 dni pracy
[✓ Zatwierdź]  [✕ Odrzuć]  Szczegóły ›
— below the fold —
ZAPAS CZASU (chart)                         | NAJBLIŻSZE 7 DNI (absences starting/ending,
                                            |  tasks starting, task ends, the deadline)
PRZYCZYNY ZMIANY od raportu z pt 6 lis (92 → 39 na 100)
 • Bez nieobecności Bartosza szansa byłaby 64 na 100.
 • Bez wydłużenia „API katalogu” szansa byłaby 80 na 100.
GŁÓWNE RYZYKA
 • „API katalogu”: im dłużej trwa, tym później koniec projektu.
```
- No decision pending: block 3 reads "Nic nie czeka na Twoją decyzję. Następny raport: {dzień}"
  with "🎤 Raport".
- Approve/reject from the Pulpit works in place (same rules as 8.4); "Szczegóły" opens 8.4.

### 8.3 Raport (WP15)
```
Raport · pt 13 lis (zmień datę)                         ostatni raport: pt 6 lis
1 ZDARZENIA OD OSTATNIEGO RAPORTU
 [ Np. „Bartek od jutra chory do poniedziałku. API skończone, makiety w połowie.” ] 🎤
 Podpowiedzi: [Ktoś będzie nieobecny] [Zadanie skończone] [Zadanie potrwa dłużej] [Nowe zadanie]
 [ Postęp zgodny z planem ]
2 DO POTWIERDZENIA — Zaznacz zmiany, które się zgadzają.            Zaznacz wszystkie
 ☐ 🧍 Bartosz nieobecny od pon 9 lis, wraca pon 16 lis        [✎] [✕]
 ☐ ✅ „API katalogu” skończone w czw 12 lis                   [✎] [✕]
 ? Który poniedziałek? [pon 9 lis] [pon 16 lis]        (amber card, blocks saving)
 NIEROZPOZNANE FRAGMENTY: „i tak dalej” → Dodaj ręcznie
3 WPŁYW NA PROJEKT
 Szansa 92 → 39 na 100 · Koniec 18 gru → 22 gru                  (Liczę… while computing)
 [ Zapisz raport ]                                           Wypełnij formularz ›
```
- Report date defaults to today; "zmień datę" opens a date field.
- Hint chips insert a sentence start ("Nieobecny będzie …").
- Cards **unchecked by default**; "Zapisz raport" is enabled when at least one card is checked or
  "Postęp zgodny z planem" was used; open questions block saving.
- "Postęp zgodny z planem": every running task gets the progress the plan expected by the report
  date; shown as cards to confirm like any other item.
- **"Wpływ na projekt"** is a dry-run forecast of the draft (not saved), recomputed after each
  change of the checked set, debounced; shows "Liczę…" meanwhile.
- The existing warning stays: running tasks without news → "3 zadania w toku bez wieści — czy od
  {data} nic się nie zmieniło?".
- "Wypełnij formularz" opens the per-task form (v1 functionality, restyled).

### 8.4 Decyzja (WP15)
```
‹ Pulpit     Decyzja do podjęcia · ważna do czw 12 lis (zostały 3 dni)
Celina przejmuje zadania Bartosza na czas jego nieobecności
ⓘ Dotyczy ludzi, dlatego wymaga Twojej zgody.
SKUTEK  | Szansa 39 → 67 na 100 ▲ | Koniec 22 gru → 18 gru ▲ | Budżet 92 → 94 dni pracy ▼ |
UZASADNIENIE  „API katalogu” blokuje testy, a Bartosz wraca dopiero 16 lis. Celina zna to zadanie
              i ma wolne dni. Osoba tymczasowa dałaby mniej (58 na 100) i kosztowałaby 6 dni pracy.
KOGO DOTYCZY  Celina: przejmuje „API katalogu”, 2 dni na wdrożenie · Bartosz: po powrocie wraca do swoich zadań
KOSZT ZWŁOKI  Każdy dzień czekania to ok. −2 na 100.
[✓ Zatwierdź]  [✕ Odrzuć]  [✎ Popraw]  [Odłóż decyzję]
SZCZEGÓŁY ▾  • Wszystkie rozważone możliwości (table incl. "Bez zmian": szansa, koniec, budżet)
             • Skąd te liczby (finish-date distribution of the worlds against the deadline)
             • Wyjaśnienie prostymi słowami (AI) — on request, as today
```
- "Uzasadnienie" is **generated by code from the numbers** (contrastive: the chosen option vs the
  best alternative), never by the LLM; the AI explanation stays an optional extra in Szczegóły.
- Arrows: green ▲ = better for the project, red ▼ = worse (budget up is ▼).
- "Odrzuć" expands in place: the four reasons as chips; "Inny powód" reveals the text box with the
  microphone (the same component as in Raport); "Potwierdź odrzucenie" · "Anuluj".
- "Popraw" shows the one parameter (§3) as a select; effects recompute; "Zatwierdź" then applies
  the corrected version.
- The promise equals the result after approval (existing WP12 guarantee and test).
- Project tab "Decyzje": the pending one(s) on top, then the project's archived decisions (a
  filtered Dziennik).

### 8.5 Nowy projekt — kreator (WP15)
1. "Podstawy": name, start, deadline (examples inside the fields); "Więcej" → company days off.
2. "Zespół": paste a list, add one by one, or dictate ("Anna, programistka; Bartek, programista").
3. "Zadania": three large cards — "Zaimportuj arkusz" (with "Pobierz przykładowy arkusz"),
   "Opisz słowami lub głosem", "Wpisz w tabeli"; recognised tasks appear as "Do potwierdzenia"
   cards (same pattern as 8.3).
4. "Gotowe": "Plan gotowy: zdążymy w {N} na 100" → Pulpit.
- **No absence-frequency question**; the team default as in §2. Budget follows from the plan and
  is shown as information ("Budżet z planu: 84 dni pracy" with "Zmień").

### 8.6 Dziennik (WP16)
- Global (sidebar) and per project (tab). Filters: "Wszystko" · "Decyzje" · "Raporty" · "Zmiany
  planu". Grouped by day, newest first. Entry: time · actor ("Ty" / "Sentinel") · one sentence ·
  effect chip ("92 → 39 na 100") · expand (▸) to the full brief as it was then and its fate
  (§3 lifecycle, rejection reason).
- Top: "Szansa w czasie" line chart with a dot per report/decision; clicking a dot scrolls to it.
- "Pobierz dziennik (CSV)".

### 8.7 Plan (WP16)
- Tabs "Harmonogram" · "Zadania" · "Zespół". Harmonogram: Gantt of the current residual plan, the
  "dziś" line, the deadline, the forecast band; done tasks grey, running blue, tasks in "Główne
  ryzyka" amber; absences as hatched bands. Zadania: name, state, progress, planned end, people,
  depends on; not-started tasks editable (WP12 corrections). Zespół: person, role, absences
  (dates), current and next tasks, **workload** next week — no performance metrics.
- "Pobierz plan (CSV)".

### 8.8 Laboratorium (WP16)
- **"Co jeśli?"** on a chosen project: scenario cards "Osoba nieobecna" (kto, od, do) · "Zadanie
  potrwa dłużej" (które, o ile dni) · "Nowe zadanie" (nazwa, dni, po czym, kto); shows "Wpływ na
  projekt" (the same dry run as 8.3), nothing saved; "Dodaj do raportu" opens Raport with these
  items as checked cards.
- **"Symulator"**: the existing simulator restyled; "Mało zakłóceń" / "Dużo zakłóceń"; "Sentinel"
  vs "Bez reakcji"; +1 dzień / +5 dni / "Do końca" with a day counter; ends with one sentence for
  the board.

### 8.9 Kalendarz (WP16, a section of "Ustawienia projektu")
- "Kopiuj link do kalendarza" (secret token URL, `.ics`), three-step instructions for Google
  Calendar and for iCloud; "Unieważnij link"; warning: "Kto ma ten link, widzi imiona osób i daty
  nieobecności."
- Feed: the deadline; task starts and ends (plan); absences (dates only, never reasons); decision
  validity dates; weekly report reminder (default **Thursday 17:00**, changeable).

### 8.10 Ustawienia (WP16)
- Application: "Wygląd" (Jasny default / Ciemny / Systemowy), "Język", "Model AI" ("Chmura
  (zalecany) — dokładniejszy" / "Lokalny — dane nie wychodzą z firmy, wolniejszy"), keys only in
  the installed version (no settings page in the demo, as today).
- Project: basics, team, company days off, calendar, report reminder day and hour, exports,
  "Jak Sentinel podejmuje decyzje" (fixed text, §3), "Usuń projekt" in a red zone at the bottom.

## 9. Voice component (WP15; used everywhere a text box takes speech)

- Click 🎤 → recording state: red dot, elapsed time, level meter, and two buttons **✓** (or Enter)
  and **✕** (or Esc). No visible time limit; a technical cap of 5 minutes with a warning at 4:30.
- **Live preview**: while recording, the audio so far is sent to the server about every 3 s (one
  request in flight at a time; skip a tick if the previous is still running) and transcribed by
  Groq Whisper; the preview text appears **grey** at the cursor position. On ✓ the whole
  recording is transcribed once more and replaces the preview as **normal (black) text**. On ✕
  the recording and the dictated span are removed; text that was in the box before stays.
- Preview requests do not count against the demo's daily AI cap; the final transcription does.
  Groq free-tier limits: if a preview is refused (429), keep recording and show "Podgląd chwilowo
  niedostępny" — the final transcription still runs.
- Privacy as in WP14: audio and text are never stored or logged; the request log records only
  that a transcription happened and its length.
- Errors in plain words (no microphone permission, no key, provider down); the button is hidden
  without a Groq key.

## 10. Acceptance for v2

- Every v2 screen in Polish and English, light and dark, screenshots at 1440×900 and 1280×800 in
  `docs/ui/v2/`.
- The internal-term checker and the translation tests cover v2; the accessibility scan has no
  serious violations (light and dark).
- The demo path works end to end on `/v2` in demo mode (e2e test): Start → showcase Pulpit →
  Raport by voice (fake microphone) → Do potwierdzenia → Wpływ na projekt → Zapisz → Pulpit →
  Decyzja → Zatwierdź → Pulpit shows exactly the promised numbers.

## Sources

Bar & Neta 2006, *Psychological Science* · Buehler, Griffin & Ross 1994, *JPSP* · Cowan 2001,
*BBS* · Deming 1986, *Out of the Crisis* · Dietvorst, Simmons & Massey 2015, *JEP: General*; 2018,
*Management Science* · Edmondson 1999, *ASQ* · Endsley & Kiris 1995, *Human Factors* · EU AI Act,
Regulation (EU) 2024/1689 (Art. 5(1)(f), 12, 14; Annex III point 4) · Few 2006, *Information
Dashboard Design* · Fitts 1954 · Flyvbjerg 2006, *Project Management Journal* · Galesic,
Garcia-Retamero & Gigerenzer 2009, *Health Psychology* · Gigerenzer & Hoffrage 1995, *Psych.
Review* · Goldratt 1997, *Critical Chain* · Goodhart 1975; Strathern 1997 · Healey & Enns 2012,
*IEEE TVCG* · Hick 1952 · ISO 24495-1:2023 · Kahneman & Tversky 1979, *Econometrica* · Leach 2014,
*Critical Chain Project Management* · Lee & See 2004, *Human Factors* · Mark, Gudith & Klocke 2008,
*CHI* · Miller 2019, *Artificial Intelligence* · Mosier & Skitka 1996 · Parasuraman & Riley 1997,
*Human Factors* · Parasuraman, Sheridan & Wickens 2000, *IEEE SMC-A* · Spiegelhalter, Pearson &
Short 2011, *Science* · Sweller 1988, *Cognitive Science* · Tversky & Kahneman 1981, *Science* ·
Ware 2012, *Information Visualization* · WCAG 2.2.
