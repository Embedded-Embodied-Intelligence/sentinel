# Sentinel: UI design brief

Version 1.0 · 30 Oct 2026 · Target: `src/sentinel/app/ui/` (Jinja templates, htmx, one stylesheet `static/sentinel.css`)

**Goal.** The app should feel calm, trustworthy and data-forward. A business manager opens a project and within five seconds knows two things: *are we going to make the deadline?* and *what do I need to decide?* Everything else stays one click away.

**Constraints.** Server-rendered HTML with htmx and one hand-written CSS file. No external fonts, icon CDNs or other network assets: use the system font stack and inline SVG icons. Must meet WCAG 2.2 AA, with focus always visible and status never shown by colour alone. Token names in §2 match the existing custom properties in `sentinel.css`, so the new values can replace the old ones directly; tokens marked **new** are additions.

**Research basis.** Web screens on Mobbin from PayPal, Wise, Mercury, Linear and Asana, Oct 2026. I took patterns and principles only (see Appendix A). The Mobbin account showed about two highlight screens and one onboarding flow per app. Stripe and Revolut Business showed only marketing screens, so Mercury, Linear and Asana stand in for them. No toast or dense-table screens were visible, so those two components follow the principles below rather than any one source.

---

## 1. Design principles

1. **One hero number per screen.** Put a label above the number, make the number large, and put the change since last time right below it as an arrow, words and a reference point. *From:* PayPal crypto detail (a big price, then "↓ $1,995.41 (3.27%) Past 24 hours"), Mercury home ("Mercury balance" with in/out arrows), Wise home ("Total balance"). *Sentinel:* the chance of meeting the deadline on Overview; chance before → after on Recommendation; the simulated day on Simulator.
2. **Actions sit next to the number they change.** *From:* Wise places Send · Add money · Request chips directly under the balance; Mercury places a Send · Transfer · Deposit row under the greeting; PayPal puts Send/Request at the top of its right rail. *Sentinel:* put "Nowy raport" and "Zapytaj Sentinela" directly under the hero number, not at the bottom of a long card.
3. **Consequential decisions get a focus mode, and the page itself is the review.** *From:* Wise's transfer flow drops the global navigation and shows a named step bar (Recipient · Amount · Review · Pay), a close ✕, one centred column, and summary rows with "Change" links. *Sentinel:* the wizard and the recommendation page run without the sidebar. The recommendation page reads as a review: what changes, what it costs, then one decision.
4. **Ask one question at a time, and say why.** *From:* PayPal sign-up asks one thing per screen with a single "Next"; Mercury titles each step as a question ("What is your company's name?") and reassures underneath ("doesn't have to be your legal name, you'll add that later"). *Sentinel:* wizard step titles are questions, and the helper text says why we ask and that the answer can change later.
5. **Show the next step and fold the rest.** *From:* Mercury's setup expands the current step as a card, collapses later steps into rows and adds a side timeline; Linear's AI answer hides its work behind "Worked for 17 seconds ▸"; Asana uses "Show more". *Sentinel:* methodology, "200 symulacji", the full options table and cost-unit explanations go behind "Szczegóły".
6. **Keep the chrome quiet; colour always means something.** *From:* Linear and Mercury use a grey sidebar, a white canvas, one accent and small muted labels; Mercury shows "–" for empty values instead of noisy zeros. *Sentinel:* neutral greys and one teal accent. Green, amber and red appear only for status, always with an icon and a word.
7. **Every button names its consequence, and the way out is visible but quiet.** *From:* PayPal "Agree and Create Account"; Mercury's primary button relabels itself to "None of the above →" to match the current state; Mercury "Skip this step"; PayPal "Not now". *Sentinel:* use buttons such as "Zatwierdź zastępstwo", "Zapisz raport (bez zmian)", and a tertiary "Zdecyduj później".
8. **Empty states teach by example.** *From:* Linear's welcome screen has one sentence, one input and three example cards; Asana puts a dashed "Create project" tile first in its project grid. *Sentinel:* use this pattern for the Start page with no projects, History with no events, and the Simulator before its first run.

---

## 2. Design tokens

Put the tokens on `:root`, add dark values under `@media (prefers-color-scheme: dark)`, and (optional) add `:root[data-theme="dark"|"light"]` overrides if a theme switch is added later. Contrast ratios were computed with the WCAG 2.x formula and checked programmatically.

### 2.1 Colour: light

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `--bg` | `#F6F7F9` | page canvas | n/a |
| `--surface` | `#FFFFFF` | cards, sidebar, inputs | n/a |
| `--surface-2` | `#F0F2F5` | table header, KPI strip, chips, zebra rows | n/a |
| `--border` | `#DFE3E8` | dividers, card outlines (decorative) | n/a |
| `--border-strong` | `#7C8693` | input borders, radio and checkbox outlines | 3.69:1 on surface, 3.44:1 on bg (UI ≥ 3:1 ✓) |
| `--text` | `#15181D` | primary text, hero number | 17.8:1 on surface |
| `--text-2` | `#3B424D` | secondary text | 10.1:1 on surface, 9.0:1 on surface-2 |
| `--muted` | `#596371` | labels, captions, meta | 6.1:1 on surface, 5.7:1 on bg, 5.4:1 on surface-2 |
| `--primary` (accent, "Sentinel teal") | `#0B6872` | primary button, links, active nav, selection | white on it 6.5:1; on surface 6.5:1 |
| `--primary-hover` | `#08555D` | hover/pressed | white on it 8.5:1 |
| `--primary-ink` | `#FFFFFF` | text on primary | n/a |
| `--primary-soft` **new** | `#E2F1F2` | selected row/card, "czeka na decyzję" badge | primary text on it 5.6:1 |
| `--link` | `#0B6872` | inline links (always underlined) | 6.5:1 |
| `--focus` | `#0B6872` | focus ring (2 px, 2 px offset) | 6.5:1 on surface, 6.1:1 on bg |
| `--good` / `--good-bg` | `#17703A` / `#E5F3EA` | on track, improvement | 5.4:1 |
| `--warn` / `--warn-bg` | `#8A5100` / `#FFF2D9` | needs attention | 5.8:1 |
| `--bad` / `--bad-bg` | `#B3261E` / `#FCEBEA` | deadline at risk, worse | 5.7:1 |
| `--info` / `--info-bg` | = `--primary` / `--primary-soft` | info callouts | 5.6:1 |
| `--neutral` / `--neutral-bg` | `#3B424D` / `#EBEEF2` | draft, unknown, "może poczekać" | 8.7:1 |
| `--danger` / `--danger-hover` | `#B3261E` / `#8E1E18` | **delete only** | white on it 6.5:1 / 8.9:1 |
| `--toast-bg` **new** | `#1D232B` | toast background (text `#FFFFFF`) | 15.8:1 |
| `--chart-done` | `#6B7480` | finished task bars | 4.7:1 (graphic ≥ 3 ✓) |
| `--chart-running` | `#0B6872` | in-progress bars | 6.5:1 |
| `--chart-planned` | `#9CCFD4` | planned bar fill (decorative) + 1 px `--primary` border | border vs fill 3.8:1 |
| `--chart-away` | `#B86200` | absence hatch | 4.4:1 |
| `--chart-original` | `#858F9B` | original-plan line | 3.3:1 |
| `--chart-band` | `#F6F7F9` | zebra rows | n/a |
| `--chart-grid` | `#E3E7EC` | grid lines | n/a |
| `--chart-window` **new** | `rgba(11,104,114,.10)` | forecast window band | decorative, labelled |

### 2.2 Colour: dark

| Token | Hex | Contrast |
|---|---|---|
| `--bg` / `--surface` / `--surface-2` | `#0F1215` / `#171B20` / `#1F252C` | n/a |
| `--border` / `--border-strong` | `#2E353E` / `#6E7987` | strong: 3.9:1 on surface |
| `--text` / `--text-2` / `--muted` | `#E8EBEE` / `#C2C9D1` / `#9BA5B1` | 14.5 / 10.4 / 6.9:1 on surface |
| `--primary` / `--primary-hover` / `--primary-ink` | `#5CC3CC` / `#86D5DC` / `#06272B` | ink on primary 7.6:1; primary on surface 8.4:1 |
| `--primary-soft` | `#123338` | primary on it 6.5:1 |
| `--link` / `--focus` | `#6FCBD3` | 9.2:1 on surface |
| `--good` / `--good-bg` | `#6FD08E` / `#13301D` | 7.6:1 |
| `--warn` / `--warn-bg` | `#F0C060` / `#33280E` | 8.6:1 |
| `--bad` / `--bad-bg` | `#FF9B90` / `#3A1815` | 7.8:1 |
| `--neutral` / `--neutral-bg` | `#C2C9D1` / `#262C34` | 8.4:1 |
| `--danger` / `--danger-hover` | `#FF9B90` / `#FFBDB5` (text `#0F1215`) | 9.3:1 |
| `--toast-bg` | `#E8EBEE` (text `#15181D`) | 14.9:1 |
| charts: done / running / planned / away / original | `#8A94A0` / `#5CC3CC` / `#2C6970` (+ primary border) / `#E89A4A` / `#6E7987` | 5.6 / 8.4 / border 3.0 / 7.5 / 3.9:1 |
| `--chart-band` / `--chart-grid` / `--chart-window` | `#1B2026` / `#2A3038` / `rgba(92,195,204,.12)` | n/a |

**Colour rules.** The accent appears in at most three roles per screen: primary button, active navigation, and current selection/links. Status colours are never decorative: done bars are grey, not green, and the deadline line is ink, not red. Never place text on a chart fill.

### 2.3 Typography

Font stack: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. Use `font-variant-numeric: tabular-nums` on every number in KPIs, tables, chips and the Gantt axis. The base size is 16 px; never go below 12 px.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `--fs-display` | 56/60 (40/44 below 768 px), `letter-spacing:-0.02em` | 600 | the single hero number |
| `--fs-h1` | 28/36 (24/32 mobile) | 600 | page title, wizard question |
| `--fs-h2` | 20/28 | 600 | card and section titles |
| `--fs-h3` | 16/24 | 600 | sub-sections, list item titles |
| `--fs-kpi` | 22/28 | 600 | KPI values, "after" value in chips |
| `--fs-lead` | 18/28 | 400 | intro paragraph (How it works, empty states) |
| `--fs-body` | 16/24 | 400 | body text |
| `--fs-small` | 14/20 | 400 (labels 600) | table cells, field labels, meta |
| `--fs-caption` | 13/18 | 500 | KPI labels, helper text, badge text |
| `--fs-overline` | 12/16, uppercase, `letter-spacing:.06em` | 600 | eyebrows such as "CZEKA NA TWOJĄ DECYZJĘ", sidebar group titles |

Paragraphs max out at 68ch. Buttons are 15/20 at weight 600.

### 2.4 Spacing, radii, shadows

- **Spacing (4 px base):** `--space-1` 4 · `-2` 8 · `-3` 12 · `-4` 16 · `-5` 24 · `-6` 32 · `-7` 48 · `-8` 64. Card padding is 24 (16 on mobile). Gaps are 24 between cards (16 on mobile) and 48 between page sections. Label → input is 8, input → helper 4, and fields are 24 apart.
- **Radii:** `--radius-sm` 6 (chips, small tiles) · `--radius` 8 (buttons, inputs) · `--radius-lg` 12 (cards, toasts, choice cards) · `--radius-pill` 999 (badges, segmented control).
- **Shadows:** cards use a 1 px `--border` and no shadow. `--shadow-1: 0 1px 2px rgba(16,24,40,.06)` covers the selected segment and sticky bars once scrolled. `--shadow-2: 0 8px 24px rgba(16,24,40,.14)` covers toasts, menus and the drawer. Dark mode drops shadows in favour of `--border` plus the next surface step.

### 2.5 Layout, breakpoints and motion

- **Breakpoints:** `sm 480` · `md 768` · `lg 1024` · `xl 1280` (min-width queries).
- **Containers:** page content max 1120 px; reading pages and forms 680 px; focus flows 560 px (wizard step 3 and the comparison table use 960 px).
- **Grid:** 12 columns / 24 gutter at ≥ 1024; 8 / 16 at 768–1023; 4 / 16 below 768. Side gutters are 16 (mobile), 24 (tablet) and 32 (desktop).
- **Shell:** a 240 px sidebar at ≥ 1024; below that, a 56 px top bar plus a drawer.
- **Targets:** at least 44 × 44 px for anything clickable on touch, and at least 24 × 24 elsewhere (WCAG 2.5.8).
- **Motion:** 120 ms for hover/press and 200 ms for disclosure and toast, `ease-out`. `prefers-reduced-motion: reduce` turns off all transitions. No count-up animation on numbers.

---

## 3. Components

The class names are suggestions, plain BEM-lite with no framework. Every component must work with keyboard only, at 200 % zoom, and in both themes.

### 3.1 App shell and navigation (`.shell`, `.sidebar`, `.topbar`)

```
+----------------+---------------------------------------------------+
| [#] Sentinel   |                                                   |
|                |   (page content, max 1120, gutter 32)             |
| > Projekty     |                                                   |
|   Symulator    |                                                   |
|   Jak to dziala|                                                   |
|   Ustawienia   |                                                   |
| -------------- |                                                   |
| TWOJE PROJEKTY |                                                   |
| (x) Nowa odsl..|                                                   |
| (v) Wdrozenie..|                                                   |
|                |                                                   |
| [PL|EN]  v1.1.2|                                                   |
+----------------+---------------------------------------------------+
```

- **Sidebar (≥ 1024):** `--surface`, 1 px right border. Wordmark "Sentinel" in text (18/24, 600) with the existing square mark. Nav items are 40 px tall with a 20 px icon and a 15/20 label at weight 500. The active item gets a `--primary-soft` pill, `--primary` text and `aria-current="page"`.
- **"Twoje projekty" group (pattern: Asana's Projects and Mercury's Bookmarks):** up to five projects, each with a status icon and a truncated name; the full name goes in `title` and in screen-reader text that includes the status word.
- **Bottom of the sidebar:** the PL | EN segmented switch (set the `lang` attribute on change) and the version in muted 12 px. The current page footer is removed.
- **Below 1024:** a top bar with a ☰ "Menu" button, the wordmark and the language switch. The drawer slides in from the left, traps focus and closes on Esc.
- **Focus mode** for the wizard and the recommendation decision: no sidebar. The top bar shows "← Wróć" (or the wordmark) on the left, the step bar or project name in the middle, and "Zapisz i wyjdź" or ✕ on the right.
- The first focusable element is a skip link: "Przejdź do treści".

### 3.2 Page header (`.page-head`)

- Show a breadcrumb (14/20 muted) only at depth ≥ 2: `Projekty / Nowa odsłona sklepu`.
- H1, then a meta line (14/20 muted): `Stan z pt. 13 lis · Termin pt. 18 gru`.
- Page actions sit on the right: at most one primary and one secondary, wrapping below the title on mobile.
- **Project tabs** under the header: Przegląd · Raport · Historia · Ustawienia. Each tab is 44 px tall; the active one gets a 2 px `--primary` underline, weight 600 and `aria-current="page"`. On mobile the tabs scroll horizontally with a fade at the edge.

### 3.3 Hero metric card (`.hero`)

```
+--------------------------------------------------------------------+
| Szansa na dotrzymanie terminu                        Jak liczymy? |
| 39 %   (x Termin zagrozony)                                        |
| v o 55 pkt proc. od raportu z pt. 6 lis                            |
|                                                                    |
| |------------o::::|:::::::::::::::::::::|                          |
|  dzis    najpewniej 21 gru  termin 18 gru   gorzej 31 gru          |
|                                                                    |
| [ Nowy raport ]  [ Zapytaj Sentinela ]                             |
+--------------------------------------------------------------------+
```

- **Label:** 14/20, weight 500, `--text-2`.
- **Number:** `--fs-display`, tabular, `--text` (never coloured). The status badge (§3.5) sits on the number's baseline and wraps below it on mobile.
- **Delta line:** 14/20 with an arrow icon, words and a reference date. Use `--bad` for worse, `--good` for better, and `--muted` with "bez zmian" for no change. A screen reader reads it as "spadek o 55 punktów procentowych".
- **Forecast window strip** (data-forward and new): an 8 px `--surface-2` track runs from today to the bad-case finish. A `--chart-window` band spans most-likely to bad-case, a 2 px `--text` tick marks the deadline, and a 12 px `--text` dot marks the most likely finish. Labels sit below in 13/18 muted. The strip is `aria-hidden` because the KPI strip (§3.4) carries the same facts in text.
- **"Jak liczymy?"** is a tertiary disclosure that opens: "Policzone na 200 symulacjach od dzisiejszego stanu. Szansa to odsetek symulacji, które kończą się przed terminem."
- **Loading:** show "— %" in a muted skeleton and the line "Liczę prognozę… zwykle kilka sekund" with `aria-live="polite"`. This mirrors Wise's "can take up to 1 minute" expectation-setting.
- **Status thresholds:** keep the existing `chance.level.*` mapping from the code.

### 3.4 KPI tiles (`.kpi-strip`, `.kpi`)

Pattern: Mercury's Bill Pay card ("Outstanding · Overdue · Due soon"), which is one quiet row of stats separated by dividers rather than five grey boxes.

```
| Termin       | Najpewniej skonczymy | W gorszym wariancie   | Budzet           |
| pt. 18 gru   | pon. 21 gru          | czw. 31 gru           | 27 z 84 osobodni |
|              | ! 1 dzien rob. po    | x ok. 2 tyg. po       | [####------] 32 %|
|              |   terminie           |   terminie            | Prognoza: 108 %  |
```

- **Tile:** a 13/18 muted label, a value in `--fs-kpi`, and an optional sub-line in 13/18. The sub-line carries an icon and the status colour only when it describes a status. Show "–" when a value is missing.
- **Budget tile:** a 4 px progress bar (`--chart-running` on `--surface-2`) with the percentage in text. "Szansa zmieszczenia się w budżecie: 23 %" goes behind the tile's details.
- **Layout:** 4 columns at ≥ 1024, 2 × 2 at 480–1023, and below 480 a list of rows with the label on the left and the value right-aligned (pattern: Mercury Accounts list).
- The strip lives inside the hero card, below a 1 px divider.

### 3.5 Status badge (`.badge`)

- **Shape:** a 24 px pill with 8 px horizontal padding, a 4 px gap, a 14 px icon and text in 13/16 at weight 600. Background is `--{status}-bg`, text is `--{status}`.
- **Variants** (the icon is `aria-hidden`; the word carries the meaning):

| Variant | Icon | PL text | Tokens |
|---|---|---|---|
| good | ✓ check | Na dobrej drodze | good |
| warn | ! circle | Wymaga uwagi | warn |
| bad | ✕ circle | Termin zagrożony | bad |
| decision | clock | Czeka na decyzję | primary-soft / primary |
| later | clock outline | Może poczekać | neutral |
| draft | dot | Szkic | neutral |
| auto | gear (cog) | Automatycznie | neutral |

- Never use a bare coloured dot. Badges never act as buttons.

### 3.6 Recommendation card (`.rec-card`), list form on Overview

```
+--------------------------------------------------------------------+
| CZEKA NA TWOJA DECYZJE · od pon. 16 lis                            |
| Zastepstwo w zadaniu "API katalogu produktow"                      |
| Kto: Cezary Mazur · Za kogo: Bartosz Kowalski (do pon. 23 lis)     |
|                                                                    |
| +----------------+ +-------------------+ +-------------------+     |
| | Szansa         | | Koniec            | | Koszt             |     |
| | 39 % -> 55 % ^ | | 22 gru -> 21 gru ^| | +2 osobodni   v   |     |
| +----------------+ +-------------------+ +-------------------+     |
| (i) Potrzebna Twoja zgoda - zmiana dotyczy ludzi.                  |
|                                              [ Przejrzyj i zdecyduj ]|
+--------------------------------------------------------------------+
```

- **Card:** `--surface`, 1 px `--border`, `--radius-lg`. No coloured left border, because status colour is reserved.
- **Impact chips (`.delta-chip`):** `--surface-2`, `--radius-sm`, 12 px padding. Each has a 12/16 muted label and a value of "before → after" in 15/20 weight 600 with tabular figures. An arrow icon shows whether the change is better (`--good`) or worse (`--bad`), with hidden text "lepiej" or "gorzej". The order is fixed: Szansa, Koniec, Koszt, Przesunięte zadania. Show "–" for zero.
- **Primary button rule:** if any decision is pending, the first card's "Przejrzyj i zdecyduj" is the page's only primary button, and the hero's "Nowy raport" drops to secondary. Otherwise "Nowy raport" is primary. The primary always follows the most urgent action.
- Proposals marked "może poczekać" go under a disclosure: "Inne propozycje (2)".
- **No pending decisions:** show one line, "✓ Nic nie czeka na Twoją decyzję.", not an empty card.

### 3.7 Comparison table (`.compare`)

| Możliwość | Szansa na termin | Opóźnienie (dni rob.) | Koszt (osobodni) |
|---|---:|---:|---:|
| **Zastępstwo: Cezary Mazur** · `✓ Polecana` | **55 %** `[#####-----]` | 2,0 | 92 |
| Zastępstwo + nowa kolejność zadań | 53 % | 2,1 | 92 |
| Rezygnacja z „Karty podarunkowe” | 41 % | 2,7 | 84 |
| Przesunięcie terminów zadań | 37 % | 3,1 | 91 |
| Nowa kolejność zadań | 36 % | 3,1 | 91 |
| *Bez zmian: punkt odniesienia* | 39 % | 2,9 | 91 |

- **Header:** `--surface-2`, 13/18, weight 600, muted. Rows are at least 52 px with `--border` dividers. Numbers are right-aligned and tabular, with one decimal for days and none for percentages.
- **Recommended row:** `--primary-soft` background, the `✓ Polecana` badge and a bold label. Colour is never the only cue.
- **Baseline row:** "Bez zmian" is always shown, pinned last and labelled "punkt odniesienia". Other rows may show the difference from it in small muted text ("+16 pkt").
- **Mini bar:** a 64 px bar in the chance column (decorative; the number is the content).
- **Option names:** keep them under 60 characters. The long description goes in an expandable row (`Więcej`, `aria-expanded`).
- **Below 768:** each option becomes a card showing its name and three label : value rows, with the recommended card first.
- **Markup:** use `<caption>` ("Porównane możliwości") and `th scope`. The footnote ("Każdą możliwość sprawdzono na tych samych 200 symulacjach…") goes behind "Jak porównujemy?".

### 3.8 Form fields (`.field`, `.choice`, `.segmented`)

- **Label:** above the input, 14/20 at weight 600. Mark optional fields with "(opcjonalnie)" in muted text; never use asterisks.
- **Input:** 44 px tall, 12 px padding, 1 px `--border-strong`, `--radius`, `--surface`. Hover turns the border to `--text-2`. Focus adds a 2 px `--focus` outline at 2 px offset (do not rely on a border colour change alone). Disabled inputs use `--surface-2`.
- **Helper text:** 13/18 muted, linked with `aria-describedby`.
- **Error:** a 2 px `--bad` border plus an ✕ icon and message in `--bad` below the field. On submit, an error summary at the top links to each field and receives focus via htmx.
- **Live rule checks** (pattern: PayPal's password rules turning into ✓ as you type). Use these where they help, for example "✓ Termin jest po dacie startu (7 tygodni)".
- **Choice cards** for 2–4 options with descriptions (estimate certainty, disruptions, autonomy, simulator settings):
  - 1 px border, `--radius-lg`, 16 px padding, with a visible radio on the left.
  - Title 15/20 at weight 600; description 14/20 in `--text-2`.
  - Selected: 2 px `--primary` border, `--primary-soft` background and a checked radio. The whole card is the `<label>`.
  - At most 3 per row; they stack on mobile. A "Zalecane" tag uses the neutral badge.
- **Segmented control** (task status, simulator speed, history filter): 40 px tall on a `--surface-2` pill track. The selected segment uses `--surface` with `--shadow-1` and weight 600. Build it on native radios.
- **Slider + number:** a 4 px track and 20 px thumb, always paired with a number input ("27 %") so the value can be typed.
- **Dates:** a native `type=date` with `lang` set, plus a readable echo below ("pt. 13 lis 2026"). Never show the US `11/13/2026` format in the Polish UI.
- **Textarea (message for AI):** 4 rows that grow with content, an example placeholder, and a length hint.

### 3.9 Wizard stepper (`.stepper`), focus mode

```
[#] Sentinel     ==========  ----------  ----------     Zapisz i wyjdz  x
                 Podstawy v  Zespol      Zadania
```

- **Step bar** (pattern: Wise's Recipient · Amount · Review · Pay): one 4 px segment per step with a 13/18 label underneath.
  - Done: `--primary` segment, a "✓" label and a link back to that step.
  - Current: `--primary` segment, weight 600 and `aria-current="step"`.
  - Upcoming: `--border` segment with a muted label.
- On mobile the bar collapses to "Krok 2 z 3 · Zespół" over a thin progress line.
- **Body:** a 560 px column (960 px on step 3). The H1 is a question, followed by an 18/28 helper in `--text-2`, then the fields.
- **Footer:** "← Wstecz" (secondary) on the left and "Dalej: Zespół →" (primary, naming the next step) on the right. The footer is sticky on mobile.
- **Autosave note:** "Szkic zapisany · 14:02", muted, with `aria-live="polite"`.

### 3.10 Buttons (`.btn`)

| Variant | Look | When |
|---|---|---|
| Primary | `--primary` background, `--primary-ink` text; hover `--primary-hover` | at most one per view: the most urgent next step |
| Secondary | `--surface` background, 1 px `--border-strong`, `--text`; hover `--surface-2` | alternatives, including **Odrzuć** |
| Tertiary | text only in `--link`, underline on hover | "Zdecyduj później", "Zapisz i wyjdź", "Szczegóły" |
| Destructive | `--danger` background, white text | only for irreversible deletion ("Usuń projekt na zawsze") |
| Destructive-secondary | `--danger` text and border | the button that opens a delete confirmation |

- **Sizes:** sm 32, md 40 (default), lg 48 (wizard footer, decision bar, primary on mobile). Horizontal padding is 16 (20 for lg), radius `--radius` (8; deliberately not a full pill). Text 15/20 at weight 600; icons 16 px with an 8 px gap.
- **States:**
  - Focus: `:focus-visible` with a 2 px `--focus` outline at 2 px offset.
  - Disabled: `--surface-2` background, `--muted` text and `--border` border. Don't use opacity, so the label stays legible.
  - Busy: a 16 px spinner before the label, `aria-busy="true"`, and htmx `hx-disabled-elt` to stop double submits.
- **Labels:** imperative verb plus object ("Zapisz raport", "Zatwierdź zastępstwo"). A label may change with state, e.g. "Zapisz raport (bez zmian)".

### 3.11 Toasts (`.toast`)

- **Position:** bottom-left of the content area on desktop; full width minus 16 px on mobile, above any sticky bar. Only one at a time; a new toast replaces the old one.
- **Style:** `--toast-bg` with inverse text in 14/20, `--radius-lg`, `--shadow-2`, max 420 px wide. Contents are an icon, the message, an optional underlined action link and a ✕ with `aria-label="Zamknij"`.
- **Behaviour:**
  - Dismiss automatically after 6 s, or 10 s if the toast has an action. Pause on hover or focus.
  - Toasts use `role="status"` and `aria-live="polite"`. They are triggered by the htmx `HX-Trigger` response header plus a few lines in `sentinel.js`.
  - Errors that need action use an inline alert (§3.12), never a toast.
- **Copy:** the result in the past tense plus the new number, e.g. "Raport zapisany. Szansa: 39 % → 42 %." with the action "Zobacz w historii".

### 3.12 Inline alert / callout (`.callout`)

Pattern: the Wise "Check your email" callout, a tinted box with an icon and the key fact in bold.

- The background is `--{info|warn|bad|good}-bg`, with a 20 px icon on the left, an optional 15/20 title and 14/20 body text.
- Use it for "Potrzebna Twoja zgoda: zmiana dotyczy ludzi", for the demo note, for form error summaries, and for "Brak połączenia z AI".

### 3.13 Empty states (`.empty`)

- Centre the block in the content column, max 480 px wide, with 48 px vertical padding.
- Contents: an optional 40 px line icon in `--muted` (no illustrations), an H2, one sentence in `--fs-lead`, one primary and an optional tertiary.
- **Example cards** (pattern: Linear's welcome screen): three cards, each with a 20 px icon, a 15/20 title and one line of description. The whole card is a link.
- A "+ Nowy projekt" tile with a dashed `--border-strong` border can sit first in a grid (pattern: Asana).

### 3.14 Timeline (`.timeline`), for History and the simulator's "Co się wydarzyło"

Pattern: Mercury's "Application timeline", with dots on a thin rail.

```
 (v)  pon. 16 lis · Decyzja
  |   Zatwierdzono zastepstwo w "API katalogu produktow"   [39 -> 55 %]
  |
 (=)  pt. 13 lis · Raport
  |   3 zmiany: postep 2 zadan, 1 nieobecnosc              [94 -> 39 %]
```

- **Rail:** 2 px of `--border`. Nodes are 24 px circles on `--surface` with a 1.5 px `--border-strong` outline and a 14 px type icon: ✓/✕ for decisions, a document for reports, a person with a slash for absences, ⇄ for plan changes, + for new tasks, a flag for the end.
- **Entry:** a 13/18 muted meta line (`<time datetime>`), a 15/20 title at weight 600, an optional 14/20 body in `--text-2`, and an optional delta chip.
- **Grouping:** week headers as overlines ("TEN TYDZIEŃ", "6–10 LIS"). Long lists end with "Pokaż starsze (12)".
- **Markup:** an `<ol>`, newest first.

### 3.15 Gantt chart (`.gantt`, server-rendered SVG)

| Element | Encoding (each has a distinct shape, not only a colour) |
|---|---|
| Row | 32 px; name column 200 px with 13/18 `--text-2` labels, truncated with `<title>`; zebra `--chart-band` |
| Axis | on top, weekly ticks in 12/16 muted ("16 lis"), 1 px `--chart-grid` verticals |
| Done | 14 px bar, radius 4, solid `--chart-done` |
| In progress | solid `--chart-running` for the completed part + 1.5 px dashed `--chart-running` outline for the remainder |
| Planned | `--chart-planned` fill + 1 px `--primary` border |
| Original plan | a 3 px `--chart-original` line 3 px above the bar |
| Absence | the person's row with a 45° `--chart-away` hatch (2 px stroke, 4 px gap) and the label "nieobecność" |
| Threat task | a 16 px "!" in a `--warn-bg` circle before the row label, label at weight 600; title "Od tego zadania najczęściej zależy termin (7 na 10)" |
| Today | a 1 px solid `--text` line + top chip "Dziś · 13 lis" |
| Deadline | a 2 px dashed `--text` line + top flag "Termin · 18 gru" (**not red**) |
| Forecast window | a full-height `--chart-window` band from most-likely to bad-case finish, with axis labels "najpewniej 21 gru" and "gorzej 31 gru" |

- **Legend:** inline above the chart, with a miniature of each shape and a 13/18 label.
- **Interaction:** rows are focusable (`tabindex=0`). Hover or focus highlights the row in `--surface-2` and shows a tooltip with the task, dates and people.
- **Table toggle:** "Wykres | Tabela" in the card header (pattern: Mercury's chart/table toggle). The table view is the accessible equivalent: every fact from a tooltip must also appear there.
- **Below 768:** the chart scrolls horizontally inside its card with a sticky name column. The default range runs from one week before today to one week after the bad-case finish.
- **SVG semantics:** `role="img"` with `<title>` and `<desc>` ("14 zadań: 4 gotowe, 3 w toku, 7 zaplanowanych. Termin pt. 18 gru, najpewniej koniec pon. 21 gru.").

### 3.16 Disclosure (`.details`)

- Use native `<details><summary>` with a chevron that rotates 90° (no rotation under reduced motion). The summary is 15/20 at weight 600 in `--link`.
- Use it for every "Szczegóły", "Jak liczymy?", "Więcej ustawień" and "Porównaj wszystkie możliwości".

---

## 4. Screen-by-screen layouts

The layer convention is **Primary** (visible at once), **Secondary** (visible after scrolling) and **Details** (behind a disclosure or link).

### 4.1 Start: "Twoje projekty"

```
+--------------+-----------------------------------------------------------------+
| [#] Sentinel | Twoje projekty                                  [+ Nowy projekt] |
|              | Sentinel pilnuje terminu i budzetu. Decyzje naleza do Ciebie.   |
| > Projekty   |                                                                 |
|   Symulator  | +---------------------+ +---------------------+ +- - - - - - -+ |
|   Jak to...  | | Nowa odslona sklepu | | Wdrozenie CRM       |   + Nowy      | |
|   Ustawienia | | (x Termin zagrozony)| | (v Na dobrej drodze)| | projekt     | |
|              | | 39 %   v 55 pkt     | | 82 %   ^ 3 pkt      |               | |
| TWOJE PROJ.  | | szansa na termin    | | szansa na termin    | +- - - - - - -+ |
| (x) Nowa...  | | Termin pt. 18 gru   | | Termin pt. 29 sty   |                 |
| (v) Wdroz... | | (o 1 decyzja czeka) | | Raport: 2 dni temu  |                 |
|              | +---------------------+ +---------------------+                 |
|              |                                                                 |
|              | SZKICE                                                          |
|              | +-------------------------------------------------------------+ |
|              | | (2/3) Nowa odslona sklepu (szkic)                           | |
|              | |       Dodaj zadania, a policzymy szanse na termin. [Dokoncz]| |
|              | +-------------------------------------------------------------+ |
|              | PRZYKLADY                                                       |
| [PL|EN]      | Przykladowy projekt (maly) · symulator · 87 dni      [Otworz] |
+--------------+-----------------------------------------------------------------+
```

- **Primary:** the grid of real projects (3 columns at ≥ 1024, 2 at ≥ 768, 1 below). Each card shows the name (the card's single link, stretched over the card), a status badge, a 32/40 number with a delta, the deadline, and either a decision badge or the date of the last report.
- **Sort order:** projects with a pending decision first, then by chance from lowest to highest.
- **Secondary:** "Szkice", shown as rows with a step ring ("2/3", pattern: PayPal's "2/5 Set up your account") and a "Dokończ" button. "Przykłady" are kept separate from real projects.
- **Details:** none. The "Wypróbuj symulator" button leaves the header because the sidebar and the empty state cover it.
- **Empty state (no projects):** heading "Zacznij od pierwszego projektu"; the sentence "Podaj termin, zespół i zadania — Sentinel policzy, czy zdążysz."; a primary "Utwórz projekt" and a tertiary "Zobacz przykład". Three example cards: "Opisz projekt słowami", "Zaimportuj arkusz", "Wypróbuj symulator".

### 4.2 New-project wizard (focus mode: 3 steps)

**Step 1, Podstawy**

```
+-------------------------------------------------------------------------+
| [#] Sentinel    ==========  ----------  ----------    Zapisz i wyjdz  x |
|                 Podstawy    Zespol      Zadania                         |
+-------------------------------------------------------------------------+
|          Jak nazywa sie projekt i kiedy ma sie skonczyc?                |
|          Termin to dzien, do ktorego wszystko ma byc gotowe.            |
|          Mozesz go pozniej zmienic.                                     |
|                                                                         |
|          Nazwa projektu                                                 |
|          [ np. Nowa odslona sklepu internetowego                ]      |
|          Start                         Termin                           |
|          [ pt. 30 paz 2026      ]      [ pt. 18 gru 2026      ]        |
|          v Termin jest po dacie startu (7 tygodni)                      |
|          Budzet (opcjonalnie)                                           |
|          [          ] osobodni    Puste = oszacujemy z zadan.           |
|                                                                         |
|          > Wiecej ustawien (pewnosc szacunkow, nieobecnosci)            |
|                                                                         |
|                                               [ Dalej: Zespol -> ]      |
+-------------------------------------------------------------------------+
```

- "Jak pewne są szacunki?" and "Jak często zdarzają się nieobecności?" default to *Typowo* and fold under "Więcej ustawień", because few users change them.

**Step 2, Zespół: "Kto pracuje nad projektem?"**

- Show a list of role rows: role name, a number stepper for people, and the daily cost (folded; the default is 1 osobodzień). Add "+ Dodaj rolę" at the end. Names of people are optional.
- The footer has "← Wstecz" and "Dalej: Zadania →".

**Step 3, Zadania: "Jakie zadania trzeba wykonać?"** (960 px)

```
| ( ) Opisz slowami     ( ) Zaimportuj arkusz     (o) Wpisz recznie       |
|-------------------------------------------------------------------------|
| #  Zadanie                    Dni  Osoby                Po zadaniach  Opc.  |
| 1  [Warsztat wymagan       ]  [2]  [2 x backend, 1 x UX v] [ -        v] [ ]  ...|
| 2  [Projekt UX zakupu      ]  [4]  [1 x UX             v] [Warsztat.. v] [ ]  ...|
| + Dodaj zadanie                                                         |
|-------------------------------------------------------------------------|
| SPRAWDZ PRZED UTWORZENIEM                                               |
| Termin pt. 18 gru · 4 role, 6 osob · 14 zadan, ok. 38 dni roboczych [Zmien]|
+-------------------------------------------------------------------------+
| [<- Wstecz]                        [ Utworz plan i policz szanse ]      | sticky
```

- Three choice cards choose the input method. The chosen method's panel appears below them.
- **Manual table:** one "Osoby" cell (e.g. "2 × backend, 1 × UX") opens a small popover editor, replacing the five numeric role columns. "Po zadaniach" becomes a multi-select of task **names**, not numbers. "Opcjonalne" is a checkbox. Each row ends in a ⋯ menu containing "Usuń".
- **After AI extraction:** a callout says "Sprawdź, czy wszystko się zgadza", and the rows stay editable. The existing `_extract_review.html` is restyled with this pattern.
- **Review block** (pattern: Wise "Review"): a summary at the bottom of step 3 with "Zmień" links, so the wizard stays at three steps.
- **After "Utwórz":** an inline loading state ("Liczę szansę na dotrzymanie terminu… zwykle kilka sekund"), then Overview with the toast "Projekt utworzony."

### 4.3 Project overview: "Przegląd"

```
+--------------+-------------------------------------------------------------------+
| sidebar      | Projekty / Nowa odslona sklepu                                    |
|              | Nowa odslona sklepu internetowego                                 |
|              | Stan z pt. 13 lis · Termin pt. 18 gru                             |
|              | [Przeglad] Raport  Historia  Ustawienia                           |
|              | +---------------------------------------------------------------+ |
|              | | Szansa na dotrzymanie terminu                    Jak liczymy? | |
|              | | 39 %  (x Termin zagrozony)                                    | |
|              | | v o 55 pkt proc. od raportu z pt. 6 lis                       | |
|              | | |-----------o::::|:::::::::::::::|                            | |
|              | | [Nowy raport]  [Zapytaj Sentinela]                            | |
|              | |---------------------------------------------------------------| |
|              | | Termin     | Najpewniej   | W gorszym wariancie | Budzet     | |
|              | | pt. 18 gru | pon. 21 gru  | czw. 31 gru         | 27 z 84    | |
|              | |            | ! 1 dz. po   | x ok. 2 tyg. po     | [###---]   | |
|              | +---------------------------------------------------------------+ |
|              | Czeka na Twoja decyzje (1)                                        |
|              | +-- rec card (3.6) ------------------------ [Przejrzyj i zdecyduj]+ |
|              | Co zagraza terminowi                                              |
|              | +---------------------------------------------------------------+ |
|              | | ! "Testy integracyjne"     7 na 10 opoznien  [#######---]     | |
|              | | ! "API katalogu produktow" 7 na 10 opoznien  [#######---]     | |
|              | | ! "Integracja platnosci"   6 na 10 opoznien  [######----]     | |
|              | | o Bartosz Kowalski nieobecny do pon. 23 lis                   | |
|              | | o "Integracja platnosci" miala ruszyc czw. 12 lis             | |
|              | | > Jak to czytac                                               | |
|              | +---------------------------------------------------------------+ |
|              | Plan i postep                                   [Wykres|Tabela] |
|              | +-- Gantt (3.15) -----------------------------------------------+ |
+--------------+-------------------------------------------------------------------+
```

- **Primary:** the hero with the KPI strip, then pending decisions.
- **Secondary:** "Co zagraża terminowi", ranked, with a share bar and the plain sentence, then the Gantt.
- **Details:** the methodology ("200 symulacji"), the definition of "zależy termin" (under "Jak to czytać"), the expected total cost and the chance of staying in budget (in the Budget tile), and "Inne propozycje (n)".
- **"Zapytaj Sentinela"** opens an inline panel under the hero (pattern: the Linear "Ask" box): a textarea with three example prompt chips ("Co jeśli Bartek wróci później?", "Dlaczego szansa spadła?", "Co mogę zrobić sam?"). The answer appears below with "Jak do tego doszedłem ▸" folded.
- **Mobile:** the hero is full width, KPIs are 2 × 2, and the rec-card buttons are full width.

### 4.4 Check-in: "Raport statusu"

```
| Raport statusu                                                           |
| Co sie zmienilo od pt. 6 lis?                                            |
| Stan na koniec dnia: [ pt. 13 lis  v ]                                   |
| +-- Napisz wlasnymi slowami (opcjonalnie) --------------------------------+|
| | [ np. "Bartek choruje do poniedzialku, API jest w 40 %"            ]   ||
| |                                               [ Przetworz wiadomosc ] ||
| +------------------------------------------------------------------------+|
| albo uzupelnij recznie:                                                  |
| (1) Zadania w toku i najblizsze (3)                                  [^]  |
|     API katalogu produktow        ( Nie zaczete | *W toku* | Gotowe )    |
|       Wykonano  ====o--------  [ 27 ] %                                  |
|     Integracja platnosci  ! miala ruszyc czw. 12 lis  ( ... )            |
| (2) Nieobecnosci (0)                                       [+ Dodaj]     |
| (3) Zadania, ktore urosly (0)                              [+ Dodaj]     |
| (4) Nowe zadanie                                           [+ Dodaj]     |
+--------------------------------------------------------------------------+
| 2 zmiany                                   [Anuluj]   [ Zapisz raport ]  | sticky
```

- **Primary:** the date line and the task-progress section, expanded. Sections follow Mercury's checklist: numbered, with counts in the headers, and only the first one open.
- **The AI path sits at the top**, in a single box. Its result appears as "Tak to rozumiem:", a checklist of extracted changes the user can edit or untick (`_message_review.html`). Accepted items flow into the sections below.
- **Sticky footer:** a count of changes plus the primary. With zero changes the label reads "Zapisz raport (bez zmian)": a progress check without changes is valid, and the label adapts to state like Mercury's "None of the above".
- **Details:** the hint "Zgłoś stan na koniec tego dnia", and the explanation of percent done.
- **After saving:** the inline state "Liczę nową prognozę…", then Overview with the toast "Raport zapisany. Szansa: 39 % → 42 %."

### 4.5 Recommendation (focus mode)

```
+-------------------------------------------------------------------------+
| <- Przeglad · Nowa odslona sklepu internetowego                       x |
+-------------------------------------------------------------------------+
|        CZEKA NA TWOJA DECYZJE · od pon. 16 lis   (o Moze poczekac)      |
|        Zastepstwo w zadaniu "API katalogu produktow"                    |
|        Kto: Cezary Mazur      Za kogo: Bartosz Kowalski (do pon. 23 lis)|
|                                                                         |
|        Szansa na dotrzymanie terminu                                    |
|        39 %  ->  55 %        ^ +16 pkt proc.                            |
|                                                                         |
|        Co sie zmieni                                                    |
|        ---------------------------------------------------------------  |
|        Koniec              wt. 22 gru -> pon. 21 gru   ^ 1 dzien wczesniej|
|        Koszt               +2 osobodni (+2 % budzetu)  v                |
|        Przesuniete zadania -                                            |
|        Ludzie              Cezary Mazur: +4 dni w "API katalogu"        |
|        ---------------------------------------------------------------  |
|        (i) Potrzebna Twoja zgoda - zmiana dotyczy ludzi.                |
|                                                                         |
|        Dlaczego ta propozycja                                           |
|        - Bez zmian: 39 %. Z ta zmiana: 55 %.                            |
|        - Sentinel sprawdzil 6 mozliwosci; ta daje najwiecej              |
|          i najmniej zmienia plan.                                       |
|        - Druga najlepsza: zastepstwo + nowa kolejnosc (53 %).           |
|        > Porownaj wszystkie mozliwosci (6)                              |
|        > Jak to policzylismy                                            |
+-------------------------------------------------------------------------+
| [Zdecyduj pozniej]                    [Odrzuc]  [ Zatwierdz zastepstwo ]| sticky
+-------------------------------------------------------------------------+
```

- **Primary:** the title, the before → after chance (the "55 %" is in display size, the "39 %" in `--fs-h1` muted), "Co się zmieni" as Wise-style summary rows (label left, value right, direction icon), and the consent callout.
- **Secondary:** "Dlaczego", written as three bullets of no more than 20 words each.
- **Details:** the comparison table (§3.7) and the methodology.
- **Approve:** the button goes busy, the app returns to Overview, and the toast reads "Zastępstwo zatwierdzone. Szansa teraz 55 %." with "Zobacz w historii". There is no modal; this page already is the review.
- **Reject:** opens an inline panel under the bar: "Dlaczego odrzucasz? (opcjonalnie)" with chips (Osoba niedostępna · Za drogo · Inny powód), a textarea, and the buttons "Odrzuć propozycję" (secondary) and "Wróć". It is **not red**.
- **Decide later:** returns to Overview, where the card shows "Odłożone · wrócimy przy następnym raporcie".
- **Already decided:** a read-only callout "✓ Zatwierdzone pon. 16 lis" and no decision bar.
- **Mobile:** the decision bar stacks the primary on top (full width), then "Odrzuć", then the tertiary.

### 4.6 History: "Historia"

```
| Historia                         ( *Wszystko* | Decyzje | Raporty | Zmiany planu ) |
| +-- Szansa w czasie ----------------------------------------------------+         |
| |  94 %  .___.                                                          |         |
| |             \___                                                      |         |
| |                 \___. 39 %          (points = reports; deadline note) |         |
| +-----------------------------------------------------------------------+         |
| TEN TYDZIEN                                                                       |
|  (v) pon. 16 lis · Decyzja                                                        |
|   |  Zatwierdzono zastepstwo w "API katalogu produktow"       [39 -> 55 %]        |
|  (=) pt. 13 lis · Raport                                                          |
|   |  3 zmiany: postep 2 zadan, 1 nieobecnosc                  [94 -> 39 %]        |
|  (<>) pt. 13 lis · Zmiana planu  (A Automatycznie)                                |
|      Przesunieto "Interfejs katalogu" o 2 dni robocze                             |
| 6-10 LIS                                                                          |
|  ...                                                     [ Pokaz starsze (12) ]    |
```

- **Primary:** the filter and the timeline (§3.14). Every entry links to its read-only detail (a recommendation or a report snapshot).
- **Secondary:** "Szansa w czasie", a 120 px line chart with one point per report and the current value labelled at the end (pattern: Mercury's balance chart), plus a "Tabela" toggle.
- Actions taken automatically under the autonomy setting carry the "Automatycznie" badge, so the user always sees what Sentinel did on its own.
- **Empty state:** "Tu zobaczysz raporty i decyzje." with the primary "Dodaj pierwszy raport".

### 4.7 Project settings: "Ustawienia projektu"

```
| Ustawienia projektu                                         (680 px)   |
| Co Sentinel moze robic sam?                                            |
| +--------------------------------------------------------------------+ |
| | ( ) 1 Tylko doradza       Sam: nic.                                | |
| |                           Pyta o: kazda zmiane.                    | |
| | ( ) 2 Przesuwa terminy    Sam: daty zadan.                         | |
| |                           Pyta o: wszystko inne.                   | |
| | (o) 3 Zmienia kolejnosc   Sam: daty i kolejnosc zadan. [Zalecane]  | |
| |                           Pyta o: ludzi, budzet, zakres.           | |
| | ( ) 4 Dodaje osoby        Sam: takze zastepstwa i osoby tymczasowe.| |
| |                           Pyta o: rezygnacje z zadan.              | |
| +--------------------------------------------------------------------+ |
|                                                                        |
| Szacunki i nieobecnosci                                                |
| Jak pewne sa szacunki?            ( Pewne | *Typowe* | Zgrubne )       |
| Jak czesto ktos jest nieobecny?   ( Rzadko | *Czasem* | Czesto )        |
|                                                                        |
| Koszt dnia pracy                                                       |
| Programista backendu   [ 1 ] osobodzien                                |
| Programista frontendu  [ 1 ] osobodzien     > Jak liczyc koszt         |
|                                                                        |
| Eksport                                                                |
| Plan zadan (CSV)                                      [Pobierz]        |
| Historia decyzji (CSV)                                [Pobierz]        |
| Raport dla zespolu (HTML)                             [Pobierz]        |
|                                                                        |
| ---------------------------------------------------------------------- |
| Usun projekt                                                           |
| Usuwa plan, raporty i historie. Nie da sie cofnac. [Usun projekt...]  |
+------------------------------------------------------------------------+
| Masz niezapisane zmiany             [Cofnij zmiany]  [ Zapisz zmiany ] |
```

- The sticky save bar appears only when the form has unsaved changes. "Cofnij zmiany" is deliberately not "Odrzuć", which belongs to recommendations.

- **Autonomy:** four choice cards stacked as a ladder, levels 1 to 4. Each shows "Sam:" and "Pyta o:" in two short lines and avoids the word "autonomia" on screen.
- **Delete:** a destructive-secondary button that opens an inline confirmation listing what will be removed, with "Usuń projekt na zawsze" (destructive) and "Anuluj".

### 4.8 Simulator: "Symulator"

**Before the first run:** the header plus one sentence ("Zobacz, jak Sentinel prowadzi przykładowy projekt dzień po dniu, i porównaj z sytuacją, w której nikt nie reaguje."). Then one card with three groups of choice cards: Projekt (Mały · 30 zadań / Średni · 60 zadań), Zakłócenia (Spokojnie / Typowo / Burzliwie), and Kto zarządza (Sentinel / Nikt nie reaguje). Then the primary "Rozpocznij symulację". The research-settings disclaimer goes behind "Czym to się różni od wyników badań?".

**Running:**

```
| Symulator · Maly przykladowy projekt                                      |
| +----------------------------------------------------------------------+  |
| | Dzien 34 z ok. 87                 Szansa na termin  61 % (! Wymaga uwagi)| |
| | [=======================-------------------------------------------]  |  |
| | Przewin:  ( +1 dzien | +5 dni | +10 dni | Do konca )                  |  |
| +----------------------------------------------------------------------+  |
| +-- Plan i postep (Gantt) ----------+ +-- Co sie wydarzylo -------------+ |
| |                                   | | (A) dz. 34 · Sentinel przesunal  | |
| |                                   | |     "Testy" o 2 dni             | |
| |                                   | | (o) dz. 33 · Julia A. nieobecna | |
| +-----------------------------------+ +---------------------------------+ |
```

- **Primary:** the day counter as the hero, the progress bar, the step controls (a segmented-style button group; each press is an htmx request), and the chance.
- **Secondary:** the Gantt on the left (two thirds) and the event timeline on the right (one third). They stack below 1024.
- **"Do końca":** shows a progress bar with "To potrwa ok. pół minuty" and an "Anuluj" button.

**Result:**

```
| Z Sentinelem projekt skonczyl sie 10 dni roboczych wczesniej             |
| niz bez reakcji, ale wciaz 8 dni po terminie.                            |
| +-- Sentinel vs nikt nie reaguje ---------------------------------------+ |
| | Miara           Sentinel        Nikt nie reaguje    Roznica           | |
| | Zakonczenie     pon. 15 lut     pon. 1 mar          ^ 10 dni rob.     | |
| | Po terminie     8 dni rob.      18 dni rob.         ^ 10 dni rob.     | |
| | Koszt           3 590 (103 %)   3 580 (102 %)       v +10 osobodni    | |
| | Zmiany planu    3               0                                     | |
| +-----------------------------------------------------------------------+ |
| [Pokaz raport]   Uruchom ponownie                                        |
```

- The headline sentence is the result. The table includes a "Różnica" column with direction icons. "Pokaż raport" is secondary and "Uruchom ponownie" tertiary.

### 4.9 App settings: "Ustawienia"

- Use a 680 px column of cards.
- **Asystent AI:**
  - Choice cards for the provider: Groq (darmowy klucz) · Serwer firmowy · Wyłączony.
  - The fields shown depend on the provider: server address, a model select, and an API key (a password input with Pokaż/Ukryj, helper "Klucz zapisujemy tylko na tym serwerze.").
  - "Sprawdź połączenie" (secondary) shows its result as an inline callout, e.g. "✓ Połączono. Model odpowiada w 1,2 s."
  - Note in the card: "Bez AI Sentinel działa normalnie; wyłączone są tylko wiadomości pisane własnymi słowami."
- **Język i format:** PL / EN, with a date-format preview.
- **O aplikacji:** version, licence, a link to the repository, and the demo note when relevant.

### 4.10 How it works: "Jak to działa"

```
| Jak dziala Sentinel                                   | NA TEJ STRONIE  |
| Sentinel nie zarzadza projektem za Ciebie. Liczy, czy | Trzy kroki      |
| zdazysz, i podpowiada, co zmienic.                    | Skad szansa     |
|                                                       | Co robi sam     |
| (1) Zglaszasz postep  (2) Sentinel symuluje  (3) Ty decydujesz | Czego nie robi |
|  raz w tygodniu          200 mozliwych przyszlosci   zatwierdz/odrzuc | Pytania  |
|                                                       |                 |
| Skad bierze sie szansa?                               |                 |
| [ forecast window strip example ]                     |                 |
| Co Sentinel robi sam, a o co pyta  (table of 4 levels)|                 |
| Czego Sentinel nie robi                               |                 |
| Najczestsze pytania  > ... > ... > ...                |                 |
```

- Use the 680 px reading column with a lead paragraph in `--fs-lead`. The three-step explainer uses numbered circles with one sentence each and no illustrations; it stacks on mobile.
- At ≥ 1024 add a sticky table of contents on the right. The FAQ uses `<details>`.

---

## 5. Microcopy tone (Polish)

**Rules**

1. **Short.** Labels and headings run 12 words or fewer, and sentences in the primary layer 20 words or fewer.
2. **Calm and factual.** No "krytyczny", "alarm", "pilne!" or exclamation marks. Status words are "Na dobrej drodze", "Wymaga uwagi" and "Termin zagrożony".
3. **Number first, then the reason:** "39 %" comes before any explanation. Every number has an anchor: compared with the deadline, the budget or the last report.
4. **Address the user as "Ty"** (as today). Sentinel refers to itself in the third person: "Sentinel sprawdził…". Avoid bureaucratic passives such as "zostało zrealizowane".
5. **No jargon in the primary layer.** "Scenariusz", "jednostka kosztu", "łańcuch zadań", "autonomia" and "Monte Carlo" belong behind "Szczegóły". Say "symulacje" and "osobodni".
6. **Don't inflect generated names.** Use labels ("Kto: Cezary Mazur · Za kogo: Bartosz Kowalski") instead of sentences that need grammatical cases.
7. **Buttons** use the imperative plus an object: "Zapisz raport", "Zatwierdź zastępstwo", "Dokończ".
8. **Formats:**
   - "39 %" with a non-breaking space before the percent sign; "3 590" with a non-breaking space as the thousands separator; "2,1" with a decimal comma.
   - "pkt proc." wrapped in `<abbr title="punkty procentowe">`.
   - Dates as "pt. 13 lis". Lists may use relative dates ("2 dni temu"); the hero always uses absolute ones.
   - Write "Stan z pt. 13 lis", not "Stan na koniec dnia pt. 13 lis".

**Ten before → after examples from the current screenshots**

| # | Where | Before (current) | After |
|---|---|---|---|
| 1 | Overview, hero delta | ▼ o 55 punktów procentowych mniej niż przed ostatnim raportem | ↓ o 55 pkt proc. od raportu z pt. 6 lis |
| 2 | Overview, status badge | Mało prawdopodobny | ✕ Termin zagrożony |
| 3 | Overview, KPI | Zły scenariusz (1 na 10 później) | W gorszym wariancie (caption: *1 na 10 symulacji kończy się później*) |
| 4 | Overview, KPI | Najbardziej prawdopodobny koniec | Najpewniej skończymy |
| 5 | Overview, budget KPIs | Wydano do tej pory: 27 z 84 jednostek kosztu (osobodni) · Oczekiwany koszt całkowity: 91 jednostek kosztu · 23 % szansy na zmieszczenie się w budżecie | Wydano 27 z 84 osobodni · Prognoza: 108 % budżetu (*chance of staying in budget goes in the details*) |
| 6 | Recommendation, title | Zastępstwo: Cezary Mazur przejmuje udział osoby nieobecnej (Bartosz Kowalski) w zadaniu „API katalogu produktów” | Zastępstwo w zadaniu „API katalogu produktów” · Kto: Cezary Mazur · Za kogo: Bartosz Kowalski |
| 7 | Recommendation, consent | To wymaga Twojej zgody, ponieważ [dotyczy ludzi] | Potrzebna Twoja zgoda — zmiana dotyczy ludzi. |
| 8 | Recommendation, "Dlaczego" | Bez zmian szansa na dotrzymanie terminu wynosi 39 %. Sentinel rozważył możliwości (6). Na tych samych 200 symulowanych scenariuszach co prognoza na stronie przeglądu ta zmiana daje szansę 55 %… | Bez zmian: 39 %. Z tą zmianą: 55 %. Sentinel sprawdził 6 możliwości — ta daje najwięcej i najmniej zmienia plan. (*"Jak to policzyliśmy ▸"*) |
| 9 | Overview, threats | Zadanie „Testy integracyjne” decyduje o terminie w 7 na 10 scenariuszy z opóźnieniem. | „Testy integracyjne” — od nich zależy termin w 7 na 10 opóźnień |
| 10 | Settings / wizard | Szacunki i burzliwość · Jak burzliwy jest zespół? (nieobecności, niespodzianki) · Spokojny / Typowy / Burzliwy | Jak często zdarzają się nieobecności i niespodzianki? · Rzadko / Czasem / Często |

**Ready-made strings for new states**

- Start (no projects): "Zacznij od pierwszego projektu" · "Podaj termin, zespół i zadania — Sentinel policzy, czy zdążysz."
- Draft card: "Szkic · krok 2 z 3" · "Dodaj zadania, a policzymy szansę na termin." · [Dokończ]
- No decisions: "✓ Nic nie czeka na Twoją decyzję."
- No threats: "Na razie nic nie zagraża terminowi."
- Loading: "Liczę prognozę… zwykle kilka sekund."
- Toasts: "Raport zapisany. Szansa: 39 % → 42 %." · "Zastępstwo zatwierdzone. Plan zaktualizowany." · "Propozycja odłożona. Wrócimy do niej przy następnym raporcie."
- Errors: "Nie udało się zapisać raportu. Popraw pola oznaczone poniżej." · "Brak połączenia z AI. Możesz uzupełnić raport ręcznie."
- Delete confirmation: "Usunąć „Nowa odsłona sklepu”? Plan, raporty i historia znikną. Tego nie da się cofnąć."

---

## 6. Do not

- **Don't copy any studied brand:** no PayPal-style blue header bar or full-pill navy buttons, no Wise lime green, no Mercury periwinkle, no Linear purple, and no Asana coral or gradient header. Don't copy their logos, wordmarks, icons, illustrations or card shapes either.
- **Don't add a second accent colour or use status colours decoratively.** That means no green "done" bars, no red deadline line, and no coloured left borders on cards.
- **Don't show status by colour alone.** Every status needs an icon and a word, including in the Gantt and the sidebar.
- **Don't paint "Odrzuć" red or give it the destructive style.** Red buttons are only for deleting data.
- **Don't put two primary buttons in one view,** and don't make two decision buttons equally loud.
- **Don't open a modal for a routine decision.** Confirmations are inline; this includes delete.
- **Don't show methodology in the first layer:** "200 symulowanych scenariuszy", "jednostki kosztu" and "łańcuch zadań" go behind Szczegóły.
- **Don't show a number without an anchor, or a percentage with decimals.**
- **Don't load anything from the network:** no web fonts, icon CDNs or analytics. Use inline SVG and system fonts only.
- **Don't remove focus outlines.** Never use `outline: none` without a visible replacement.
- **Don't hide essential information behind hover only.** Gantt tooltips need the table view.
- **Don't use emoji as icons, and don't count up numbers in an animation.**
- **Don't use the US date format (`11/13/2026`) in the Polish UI.**

---

## 7. Acceptance checks for the implementation

- [ ] axe-core reports 0 violations on every screen in both themes and both languages.
- [ ] The full flow (create project → check-in → approve recommendation) works by keyboard alone with visible focus at every step.
- [ ] At 320 px width there is no horizontal page scroll; only the Gantt card scrolls inside itself.
- [ ] At 200 % zoom nothing overlaps or is cut off.
- [ ] Every view has exactly one primary button (or none).
- [ ] Polish strings (about 30 % longer than English) fit without truncating buttons or tabs.
- [ ] `prefers-reduced-motion` removes every transition.
- [ ] The page makes no network requests outside its own origin.

---

## Appendix A: research notes (patterns observed on Mobbin)

| App (web) | Screen(s) seen | Pattern taken | Used in |
|---|---|---|---|
| PayPal | Home dashboard; crypto detail; sign-up flow (22 screens) | Hero number + delta with period; action rail at the top; setup progress "2/5"; one question per sign-up screen; live password rules turning into ✓; buttons that name the consequence ("Agree and Create Account"); quiet escape "Not now" | §1.1, 1.2, 1.4, 1.7; §3.3, 3.8; §4.1 |
| Wise | Home dashboard; send-money "Amount" step; sign-up flow (14 screens) | Label-above balance with action chips; focus mode with a named step bar and ✕; summary rows with "Change"; tinted callout with icon and bold key fact; setting time expectations | §1.2, 1.3; §3.9, 3.12; §4.2, 4.5 |
| Mercury | Home dashboard; setup checklist; application flow (10 screens) | Calm card grid; stat row with "–" for empty; chart/table toggle; accounts list (label left, value right); expanded current step + collapsed rows; application timeline; question-as-heading with reassurance; button label follows state | §1.4, 1.5, 1.6, 1.7; §3.4, 3.14, 3.15; §4.4, 4.6 |
| Linear | Welcome / empty state; AI chat answer | Quiet chrome; empty state with one input and three example cards; collapsed "Worked for 17 seconds ▸" | §1.5, 1.6, 1.8; §3.13; §4.3 ("Zapytaj Sentinela") |
| Asana | Home dashboard | Widget cards; tabs with counts ("Overdue (6)"); dashed "Create project" tile; "Show more"; projects in the sidebar | §1.8; §3.1, 3.13; §4.1 |
| Stripe, Revolut Business | Only marketing pages were visible on the account used | n/a (replaced by Mercury, Linear, Asana) | n/a |
