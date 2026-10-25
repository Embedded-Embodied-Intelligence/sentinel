# WP9b notes — the user interface: plain-language project control for business users

**Purpose.** The WP9a engine and API get pages for project managers and business people, who
must create a project, see whether the deadline is at risk, report what happened and act on a
recommendation without training and without a technical term. The pages are a view of spec §11;
they add no semantics except the two answers and the undo of spec v2.0.1 (below).

**Stack** (ADR-0025). Jinja2 templates rendered by the WP9a FastAPI app from the services'
own views (`sentinel.app.ui`), HTMX 2.0.11 (vendored, pinned, 0BSD) for partial updates,
forms and job polling, 47 lines of own JavaScript (form rows, slider values, focus after a
refused form) and one hand-written CSS file with design tokens for light and dark mode. Charts
are server-side SVG built on the cockpit's primitives (`dashboard.svg`) with dates on the axis.
No CDN, no external request at runtime, no framework. Every string comes from a catalogue in
Polish (default) and English (`ui/text.py`, 532 keys; the application's messages in
`app/messages.py`).

**Screen map** (each screen has an empty, a loading and an error state).

| Screen | Path | Primary action | What it shows |
| --- | --- | --- | --- |
| Start | `/` | New project | project cards: name, deadline, chance of meeting it (badge, trend), decisions waiting; drafts; simulator runs; "what this is" |
| New project, step 1 | `/new`, `/projects/{id}/setup/basics` | Next | name, start date, deadline, budget, how sure the estimates are, how turbulent the team is |
| Step 2: team | `/projects/{id}/setup/team` | Next | people with roles (suggestions), a pasted list "Anna, backend"; autosave |
| Step 3: tasks | `/projects/{id}/setup/tasks?tab=…` | Create the plan | describe in words (AI, if set up), import a spreadsheet (template, per-row errors), table (days, people per role, after tasks, optional); issues as one types |
| Overview | `/projects/{id}` | Check-in | chance of meeting the deadline with its trend, deadline, most likely and bad-case finish, budget outlook, what threatens the deadline, decisions waiting, automatic changes with Undo, plan-and-progress chart (and as a table) |
| Check-in | `/projects/{id}/checkin` | Save the check-in | tasks in progress and next (status, share done, finish date, optional start and people), absences (no reason field), growing tasks, new tasks, or a message read by the AI and confirmed item by item |
| Recommendation | `/projects/{id}/recommendations/{seq}` | Approve | the action in words, its effect (chance, finish date, cost, dates moved), why approval is needed, why it was chosen, the options compared, approve / decide later / reject, or Undo |
| History | `/projects/{id}/history?show=…` | — | check-ins, recommendations, decisions and changes, filterable |
| Project settings | `/projects/{id}/settings` | Save | name, deadline, budget, autonomy in four sentences, presets, daily costs, AI proposals, downloads (plan CSV, project JSON, the detailed report), delete with confirmation |
| Simulator | `/simulator`, `/projects/{id}` | Start / 5 days | example (small J30, medium J60), turbulence, who manages it; 1, 5, 10 days or to the end; timeline of events and Sentinel's actions; comparison with nobody reacting; the report |
| Settings | `/settings` | Save | AI provider (none, local Ollama, Groq, OpenRouter), model, host, key (stored server-side, never shown again), connection test; read-only in the demo |
| How it works | `/how-it-works` | — | simulate before acting, goals, what the AI does and does not do, privacy, what the numbers mean; links to the repository and the paper |

**UX rules** (checked on every screen by `tests/ui_check.py` and the end-to-end tests).

- No internal term (spec §11.7): no action label, symbol, "makespan", "rollout", "baseline",
  "PERT", "PSPLIB", "LLM"…; the checker also rejects missing translations, raw message codes,
  ISO dates and percentages with decimals in the visible text and the labelling attributes.
- Dates as "Mon 14 Mar" / "pon. 14 mar" (with the year when it is not this year's); chances as
  whole percentages ("< 1 %", "> 99 %" at the extremes); costs with thousands separators.
- One primary button per screen; destructive actions confirmed (deletion has its own page).
- Long operations (plan, recommendation, AI reading, simulator days, report) run as jobs with a
  progress bar polled by HTMX; forecasts load after the page; nothing blocks a page.
- Keyboard: a skip link, every control reachable by Tab with a visible focus ring (3 px), radio
  groups as one Tab stop, the focus moved to a new form row and to a refused form's message.
- Labels on every input (visible or for screen readers); colour never the only signal: badges
  carry words and symbols, chips carry labels, the chart has patterns, a legend and a table.
- WCAG AA contrast in light and dark mode (axe-core: no serious or critical violation on 14
  screens); layouts work at 1280 px and on tablets from 768 px; pages are small (no framework).

**Wording** (spec §11.7). An action of several operations reads part by part, the plan part
last: "Zastępstwo: Cyrus Mazur przejmuje udział osoby nieobecnej (Ben Kowalski) w zadaniu
„Product catalogue API”" / "Substitute: Cyrus Mazur takes over Ben Kowalski's part in “Product
catalogue API”". The absent member a substitute replaces is found as SUBST does (§4): within a
role, substitutes in the order given replace the crew's absent members in increasing id order,
on the crew the recommendation saw. "Why" is composed from the recommendation's own figures:
the chance without a change and with the action, the expected delay, the deciding component in
words and the runner-up. Risk drivers read "on the critical path in 8 of 10 simulated futures".

**Spec v2.0.1** (answers to the WP9a questions). (1) SUBST onboarding stays in the remaining
work until the task is done: accepted as slightly pessimistic, stated on "How it works".
(2) Live and simulator projects hire at least one temporary worker per role,
`u ≤ max(u_min, ⌊γ R_k⌋)` with `u_min = 1`; the observation reports `u_min` (0 in research
runs, left out of serialisation), so Sentinel's candidates, their rollouts and the engine use the
same cap. A team with one tester now gets "Extra person (temporary): Tester for 10 days" as an
option (the absence case of the tests). (3) Undo: an automatic
action that changed only the plan can be undone while nothing changed after it; the `undo`
event stores the planned starts it restores, so replay needs no solver.

**Numbers on the overview.** The headline is the forecast of §11.4 (200 NoReaction rollouts),
cached per project and last change (deterministic). The trend compares it with the forecast of
the state before the latest check-in. The budget outlook adds the rollouts' mean total cost and
the share within `B`. A recommendation shows the figures of its own rollouts (§11.5); when
racing set NOOP aside early, its chance comes from 25 rollouts and can differ visibly from the
forecast (showcase: 52 % vs 39 %, 1000-rollout reference 40 %), so the page says that figure is
rough (spec question in the report).

**Tests.** `test_ui_text` (catalogue: both languages, placeholders, every key used, formats),
`test_ui_forms` (validation), `test_ui_pages` (every screen and state in both languages through
the checker; error pages with a reference id; demo CSRF and read-only settings; check-in,
decision, undo, report, deletion; AI features with a scripted model; simulator pages with the
PSPLIB data), `test_ui_e2e` (Playwright: spreadsheet → check-in → approval → history;
simulator to the end; two demo visitors; keyboard-only check-in; axe in light and dark mode).

**References.** WCAG 2.1 (W3C 2018) for contrast, focus and labels; HTMX (htmx.org); axe-core
(Deque) for the automated scan; Brooks 1995 (handover) for the substitution wording.
