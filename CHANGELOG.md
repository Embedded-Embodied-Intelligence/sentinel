# Changelog

All releases of Sentinel, newest first, compiled from the work package reports in
[`docs/reports/`](docs/reports/). Each release is a zip built by `sentinel release` from a
clean tree (`dist/`, not committed); none is tagged by the tooling. Research results are
identical across all releases (`sentinel reproduce --check`: 117 of 117 files).

## 1.10.0 — 2026-11-13 (WP19, v3 part 1: the research layer in the interface)

No change to research results (`sentinel reproduce --check`). The v2 interface shows the
research of WP18:

- **"Dowód"** at every feature tied to a decision: a point "ⓘ N" that opens a panel from the
  right with the decision, its basis ("badania", "prawo i normy", "teoria") and its evidence,
  supporting first, then challenging and nuancing; only quotes checked by code are shown, with
  their highlights, legal texts in the interface's language; `?dowod=D14` opens it directly.
- **Zasady AI**, a new group of the sidebar: **Mapa granic** (twelve processes, six criteria,
  three zones in colour, icon and word; a cell opens its reason and evidence), **Uprawnienia
  AI** (what the model may and may not do; the active model, what leaves the company and its
  latest calls as metadata only; "Próba ataku", a message with a hidden instruction through
  the real message flow, recorded by default, live on request, nothing saved), **Ludzie**
  (four features deliberately absent, the workload of the next two weeks) and **Źródła** (the
  whole registry with filters).
- **"Twoja ocena"** on the decision page (spec v2.5.0, §11.8): choose first or "Pokaż od
  razu"; the choice is stored with the decision and Dziennik shows the agreement; "Najpierw
  moja ocena" in the project settings, on by default.
- The registry, the decision catalogue (now also as data) and the boundary map ship with the
  package (`src/sentinel/evidence/data/`, ADR-0037), with English texts for the English
  interface; the OWASP items are checked against the official 2025 PDF and the Atlassian post
  against an archived copy.

## 1.9.0 — 2026-11-13 (WP18, the research layer of v3)

No change to the interface or to research results. This release adds the evidence the v3
interface and the presentation will show:

- **Evidence registry** (`docs/research/evidence/registry.json`, package `sentinel.evidence`):
  52 items for and against Sentinel's design decisions (35 from the research report, 11 new
  ones, 6 results of Sentinel's own study, RQ1–RQ5), each with its stance, a summary, one
  sentence on what follows for Sentinel and, for 40 of them, a verbatim quote of at most three
  sentences **checked by code** against the fetched source text; the other 6 say why they
  have no quote.
- `scripts/fetch_evidence.py` downloads the open sources (arXiv, NBER, PubMed, OWASP, NIST,
  W3C, the Official Journal in English and Polish, the Polish copyright act) into
  `data/evidence/` (never committed), extracts their text and checks every quote.
- **Decision catalogue** (`docs/research/decisions.md`): 24 decisions with their evidence and
  its basis; **boundary criteria and map** (`docs/research/boundary-criteria.md`,
  `boundary-map.json`): six criteria and twelve company processes in three zones.
- Legal dates checked against the Official Journal: Regulation (EU) 2026/1744 applies the
  high-risk obligations of Annex III from 2 December 2027 and replaced Article 4.

## 1.8.0 — 2026-11-08 (WP17, fixes from the audit)

- **Announced absences count at once** (spec v2.4.1, §11.3): an absence reported for a later
  day enters the forecast, the recommendations and "Co jeśli?" from its first day, instead of
  waiting for a later report. Research results are unchanged.
- **The public demo holds a crowd**: forecasts, threat lists, causes and validity dates are kept
  by the contents of a project's log and computed once for concurrent requests, and the showcase
  is copied in one transaction (15 visitors at once: 34.5 s → about 5 s).
- **Fair use of the demo's AI**: per-visitor caps of AI requests and of seconds of audio, the
  live preview counted; a sandbox only for a browser that keeps cookies (no sandbox for link
  previews, `HEAD` requests or bots), `robots.txt`.
- **Security headers** on every response: a strict content policy, no framing, `nosniff`,
  same-origin referrer, the microphone for this site only, HSTS over HTTPS.
- **v2 on every screen**: below 1180 px a narrower sidebar, below 900 px a bar on top and one
  column with scrolling tables and tabs; wide windows scale the layout up (the 1.7.0 hotfix).
- `/` opens v2 in the demo (`home = "v2"`); "Poprzedni wygląd" still leads to v1.
- The calendar link is https behind the demo's HTTPS proxy; the banner is quiet for the project
  whose Pulpit or decision page is open; "Kogo dotyczy" says nothing twice and a free option is
  "bez dodatkowego kosztu"; the Gantt chart's names shrink before the absence word.

## 1.7.0 — 2026-11-08 (WP16, interface v2, part 2)

- **Dziennik**, for all projects and per project: who ("Ty" or "Sentinel") did what, one
  sentence each, grouped by day, filters "Wszystko" · "Decyzje" · "Raporty" · "Zmiany planu",
  the effect chip ("92 → 39 na 100"), each decision's brief as it was and its fate with the
  rejection reason one click away (▸), the "Szansa w czasie" chart whose dots open their entries,
  and "Pobierz dziennik (CSV)" (no cell a spreadsheet reads as a formula). Start's recent events
  come from the same log.
- **Plan**: "Harmonogram", a Gantt chart of the current plan with today, the deadline, the
  forecast's band from the most likely to the bad-case finish, done tasks grey, running blue,
  the main risks amber with an icon and a word, absences hatched; "Zadania", with the correction
  of a task not started (days, people, dependencies, optional); "Zespół", absences by date,
  current and next tasks and next week's workload from the plan, never a performance metric;
  "Pobierz plan (CSV)".
- **Laboratorium**: "Co jeśli?" (a person absent, a task taking longer, a new task) shows the
  Raport's dry run on the latest report's day and saves nothing; "Dodaj do raportu" opens the
  Raport with the items ticked and their effect. The simulator restyled: "Mało zakłóceń" or
  "Dużo zakłóceń", Sentinel against "Bez reakcji" on the same events, "+1 dzień", "+5 dni",
  "Do końca" with a day counter, and one sentence with the result.
- **Kalendarz** (ADR-0035): a secret, revocable link to an iCalendar feed with the deadline, task
  starts and ends, absences as names and dates only, decision validity dates and the weekly
  report reminder (Thursday 17:00 unless changed); a calendar reads it without a session, and in
  the demo it works while the visitor's sandbox lives.
- **Ustawienia**: appearance, language and the AI model in plain words ("Chmura (zalecany)",
  "Lokalny"; keys only outside the demo); project settings with the basics, the team, company
  days off, the calendar, the report reminder (which also sets "Następny raport"), exports,
  "Jak Sentinel podejmuje decyzje" and "Usuń projekt" with a confirmation. No "Wkrótce" page is
  left.
- **Raport**: "Wypełnij formularz", the per-task form restyled, adds its changes as ticked cards.
- Tests: the e2e suite covers a rejection's fate in the Dziennik, "Co jeśli?" to "Dodaj do
  raportu" and the calendar feed, and the accessibility scan every v2 screen; a dev-only
  `icalendar` check reads the feed. Research results unchanged (117 of 117 files).

## 1.6.0 — 2026-11-08 (WP15, interface v2, part 1)

- A new interface under `/v2` beside the first one, which stays at `/` (link "Nowy wygląd (v2)";
  ADR-0033): light by default, dark and system themes remembered in a cookie, a glass sidebar,
  calm cards, one teal accent, status colours only for the three states and always with an icon
  and a word, body 17 px, decision buttons at least 44 px high.
- **Start**: the decisions of every project sorted by their validity date, the project tiles
  (state, verdict, "N na 100", decisions waiting), the recent events of the log with who did
  them, and three large cards on a first visit.
- **Pulpit**: the verdict ("Nie zdążymy bez zmian · Spóźnimy się o ok. 2 dni robocze"), the
  chance as "39 na 100" with a 10 × 10 dot grid and "Skąd ta liczba?", the project end and the
  budget in work-days, the pending decision with approve and reject in place, the "Zapas czasu"
  buffer chart, the next seven days, the causes of the change and the main risks.
- **Decyzja**: the effect before → after (green ▲ better, red ▼ worse), a contrastive reasoning
  written by code from the numbers, who is affected, the cost of delay, "Zatwierdź", "Odrzuć"
  with four reasons, "Popraw" (another substitute, temporary person or optional task, evaluated
  on the same worlds), "Odłóż decyzję", and the details (every option, the finish-date
  distribution, the AI explanation on request); the project tab "Decyzje" with the archive.
- **Decision model** (spec v2.4.0, §11.8): every deliberation v2 asks for runs with every
  action approved; a decision's lifecycle (pending, postponed, adjusted, approved, rejected with
  its reason, expired, superseded) is kept in the log with its time, actor and brief; its
  validity date and cost of delay are computed in the background ("ważna do czw. 19 lis",
  "Każdy dzień czekania to ok. −5 na 100"), and a decision is never applied by silence.
- **Raport**: write or dictate what happened; a live grey preview while recording (Groq's
  Whisper about every 3 s, outside the demo's AI cap), ✓/Enter and ✕/Esc, five minutes at most;
  the AI's items as cards unchecked by default with ✎ and ✕, questions that block saving, the
  parts not recognised, "Postęp zgodny z planem", and "Wpływ na projekt" as a dry-run forecast
  of the draft (ADR-0031 updated).
- **Nowy projekt**: four steps (basics, team pasted or dictated, tasks from a sheet, words or a
  table, ready with "Plan gotowy: zdążymy w N na 100" and the budget as information). No
  question about absences: one team-wide rate from ZUS's 2025 sickness-absence report, about
  4 % of working days (ADR-0034).
- Research results unchanged (`sentinel reproduce --check`: 117 of 117).

## 1.5.0 — 2026-11-05 (WP14, status messages that understand a whole report; voice input)

- A check-in message is read as a whole report: progress ("zrobiono około 15 %", "w połowie"),
  a finish with its date, a start, absences, growing tasks and new tasks, each an item to confirm;
  confirmed tasks fill their rows of the form. The owner's message of the usability rehearsal now
  gives its three items (workshop done Tue 3 Nov, the API at 15 %, Bartosz away from Thu 5 Nov,
  back Mon 16 Nov) instead of one wrong absence.
- Dates are settled by code, never counted by the model (spec v2.3.0, section 11.3; ADR-0032):
  the model names each date as a calendar date with the words it came from, the code checks the
  words on the project calendar ("od jutra" is the next working day, "do piątku" is through
  Friday, "wraca w piątek" is back that day), and a weekday that contradicts its date, a day off
  or a weekday that can name two days becomes a question on the review, never a silent shift.
  Task words match the tasks with quotes, case and inflection ignored; words that fit several
  tasks ask. The words of a date must be date words, so no reason for an absence reaches the
  cache. The review shows an absence as its first day away and its return day, with its working
  days.
- An evaluation set of 30 Polish reports on the usability and showcase projects
  (`docs/qa/ai/messages-pl.jsonl`, `scripts/messages_eval.py`): with gpt-oss-120b 43 of 43 items
  exact and no wrong date shown without a question (1.4.1: 7 of 43, 15 wrong dates); with
  qwen2.5:7b on the first 10, see `docs/reports/WP14.md`.
- Voice input beside the message box of a check-in and of "describe the project" (ADR-0031): the
  browser records at most 90 s, Groq's Whisper (`whisper-large-v3-turbo`) writes it out with the
  team's and the tasks' names as its vocabulary, and the text goes into the box to be read and
  corrected before it is processed. Neither the audio nor the text is stored; the demo's request
  log keeps only a recording's length (schema version 3) and its daily AI cap counts recordings.
  The button needs a Groq key (the provider's, or a key for recordings on Settings, which also
  tests them) and an https page or localhost.
- `scripts/voice_check.py`: the owner's message recorded (Windows' Polish voice, 15 s) written
  out in 0.5 s and read into its three items, also in the browser in demo mode by message and by
  voice; task 3 of the usability test may be done by form, message or voice.

## 1.4.1 — 2026-11-03 (WP13, the remote usability test)

- The protocol's scenario checked in demo mode on a day after the story's Wednesday 4 November,
  as a remote tester does it: the project from the spreadsheet and the pasted team, the status
  report dated 4 November saved without a question, the replacement recommendation (39 % → 67 %,
  with 11 November a holiday) and the small simulation to its end within the demo's 60-day
  steps. Nothing broke; the protocol's expected values and `baseline-timing.json` are those of
  1.4.1, and `tests/test_ui_usability.py` runs the demo's configuration and checks them.
- The demo keeps a request log per sandbox for the usability test (`request_log` in
  `configs/app_demo.toml`; ADR-0030): the time, method, route template, status, the sandbox's
  project and whether it was an HTMX request; no address, no query, no form content, deleted
  with the sandbox (schema version 2, migrated on start).
- `scripts/usability_logs.py --data-dir <demo data> --code P1` writes a tester's timeline and
  task durations with the page requests and refused forms to `docs/usability/logs/P1.md`;
  `scripts/sus_score.py` scores the SUS answer cards; the owner's steps are in
  `docs/usability/README.md`.

## 1.4.0 — 2026-11-03 (WP12, the fixes of the CEO/QA test)

- One set of numbers: a recommendation's card shows what approving it gives, since each option is
  worked out as the approval applies it (at once, on the forecast's worlds), so the overview after
  an approval shows exactly the promised chance, most likely finish, bad case and cost; the card
  shows the most likely finish of the same worlds as the overview; the plan without disruptions is
  labelled apart from the forecast's dates (spec v2.2.0, section 11.5). A substitute approved after
  a growth reported at the same work done keeps that order, so the growth no longer multiplies its
  onboarding (spec v2.2.1, section 5.1; research observations unchanged).
- The chart, the task list, the plan CSV and the HTML report show the current plan from the latest
  check-in, checked against the dependencies (those of new tasks too) with `validate_residual`, the
  original plan in its own columns; a line explains the gap to the forecast window (11.4).
- After a check-in that moved the chance by 5 points or more, the overview names up to three causes
  (each absence, growth and new task, and the progress against the plan), each the chance without
  it on the same futures (11.4).
- Polish public holidays and company days off are not working days in a live project (11.1).
- Status reports: a report without progress asks first; a date ahead is confirmed once; the change
  counter, Enter in the role field, leaving during a save and "finished on" behave; progress says
  what whole days it is saved as; a task not started that grows gets a new estimate (11.3); the
  pickers are grouped; "decide later" says what it does.
- The AI: the message review lists what it did not turn into a change and asks about unknown
  people and ambiguous tasks (clause numbers only, no message text stored); explanations in the
  page's language without internal terms (ADR-0029); a description gives short names, optional
  tasks, five working days for "about a week" and the right dependencies of a final test.
- Tasks not started can be corrected after the first check-in, each correction in the history
  (11.2); the cards say what improves when the chance does not move, mark options worse than no
  change and tell apart names cut alike; "Recalculate now"; an autonomy change says what Sentinel
  will do alone; CSV in both languages; the small items B1–B24 of `docs/qa/raport-ceo-chrome-pl.md`
  (status after WP12 at its end).

## 1.3.0 — 2026-11-02 (WP11, release readiness)

- The AI features run end to end with real models through the browser
  (`scripts/ai_live.py`, results and screenshots in `docs/qa/ai/`): a project described in a
  structured list and in free prose, a check-in message with two facts, and an explanation with
  its faithfulness badge, with `qwen2.5:7b` on Ollama and `openai/gpt-oss-120b` on Groq through
  OpenRouter. No absence reason reaches stored data, caches, logs or pages.
- A failed AI call says what went wrong (key, model, address, timeout, quota, text too long)
  and the form keeps working; a local call may take 600 s, a cloud call 90 s with two retries
  (`llm_timeout_s` in the app config); asking again after an invalid answer reaches the model
  (ADR-0028).
- A described project takes the team's role names; a role nobody in the team has stays visible
  in the task table until it is changed.
- A check-in message is read with the next working days and the factors of more work worked
  out; the review shows a growth also in days; a refused check-in keeps the confirmed items; a
  second read of a message works.
- Spec v2.1.5: in a check-in message "until Friday" ("do piątku") means away through Friday, so
  back on Monday, and "back on Friday" ("wraca w piątek") back that day; the research runs keep
  their reading.
- The settings page and the user guides recommend the cloud model (`gpt-oss-120b`) for messages
  and explanations, and the local model or a provider that does not retain data for messages
  about real people's absences; the public demo uses `gpt-oss-120b` through OpenRouter.
- An AI explanation shows action labels in words and tasks by name, says that the AI writes in
  English, can be asked again after an invalid answer and no longer holds up the project.
- `RELEASE.md` says how to install uv, what the first sync downloads, how to start the app on
  another port and how long each check takes; installed from the zip into a clean home
  directory, every step of it passes.
- The Docker image is built and run with docker compose: 653 MB on disk (156 MB compressed), the
  app answers 4 s after `docker compose up -d`, and a project made through the pages survives a
  restart and a recreated container (`scripts/docker_check.py`); `SENTINEL_PORT` sets the host
  port.
- README with the application first; user guides, deploy guide and this changelog for 1.3.0.

## 1.2.4 — 2026-10-31 (WP10, follow-up 4; spec v2.1.4)

- "What threatens the deadline" is read on 1,000 futures whose first 200 are the forecast's,
  in a background job after a check-in; chances, dates, budget and recommendations unchanged.
  The list is calmer, not stable (changes at 6 of 8 steps instead of 8).

## 1.2.3 — 2026-10-31 (WP10, follow-up 3; spec v2.1.3)

- The threats are the unfinished tasks whose realised duration has a rank correlation of at
  least 0.2 with the finish day (duration sensitivity), highest first, at most three.

## 1.2.2 — 2026-10-31 (WP10, follow-up 2; spec v2.1.2)

- The threats are the tasks on the critical chain of at least half of the late futures,
  without the always critical ones; on the QA project the list names 2–3 tasks at each of the
  9 check-ins instead of none.

## 1.2.1 — 2026-10-31 (WP10, follow-up 1; spec v2.1.1)

- The threats are ranked by the difference between late and on-time futures, from 10
  percentage points, so the plan's last task no longer tops the list; the seven minor QA
  findings are fixed, each with a test.

## 1.2.0 — 2026-10-30 (WP10, redesign and QA)

- Every screen rebuilt to the design brief (`docs/design/brief.md`, ADR-0027) in Polish and
  English, light and dark, desktop and phone.
- Exploratory QA through the browser: a 30-task project over six working weeks, both simulator
  examples and 45 wrong-use cases; 0 blockers, 9 majors fixed with regression tests
  (`docs/qa/raport-qa-pl.md`).

## 1.1.2 — 2026-10-30 (WP9d, follow-up; spec v2.0.4)

- The "similar chance" sentence appears only when a shown alternative has a higher chance.

## 1.1.1 — 2026-10-30 (WP9d; spec v2.0.3)

- In project and simulator modes the decision, the page and both explanations come from one
  record on the forecast's 200 futures, so a page never ranks an alternative above the
  recommended action and an explanation cites only figures the page shows.

## 1.1.0 — 2026-10-26 (WP9a–WP9c; spec v2.0–v2.0.2)

- The application for project managers (spec §11): live projects with check-ins, forecasts,
  threats and recommendations with an autonomy level, the simulator, a JSON API and
  `sentinel ui [--demo]` with a sandbox per demo visitor (WP9a).
- Pages in Polish and English with a three-step wizard (a description read by the AI, a
  spreadsheet or a table), the overview, check-ins, recommendations with undo, history,
  settings and "How it works" (WP9b).
- A two-stage uv Docker image with compose and an optional Ollama profile (ADR-0026), the
  public demo behind Tailscale Funnel, user guides in Polish and English and a usability test
  protocol (WP9c).

## 1.0.0 — 2026-10-24 (WP0–WP8)

- The research prototype: the formal model (spec §1–§10), PSPLIB data, SGS heuristics and
  CP-SAT, Monte Carlo forecasts, the predictive-reactive baselines and the Sentinel agent with
  its permission gate, the interpretation layer with record/replay LLM caches, 14 committed
  result runs and the generated tables and figures of the papers (`sentinel reproduce`).
- `sentinel dashboard`: a self-contained HTML cockpit of one simulated project; three examples
  in `docs/dashboard/`.
- `sentinel release`: the release zip with a generated `RELEASE.md` (WP8).
