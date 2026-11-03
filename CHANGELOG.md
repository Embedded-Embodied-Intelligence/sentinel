# Changelog

All releases of Sentinel, newest first, compiled from the work package reports in
[`docs/reports/`](docs/reports/). Each release is a zip built by `sentinel release` from a
clean tree (`dist/`, not committed); none is tagged by the tooling. Research results are
identical across all releases (`sentinel reproduce --check`: 117 of 117 files).

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
