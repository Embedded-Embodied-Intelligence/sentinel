# Changelog

All releases of Sentinel, newest first, compiled from the work package reports in
[`docs/reports/`](docs/reports/). Each release is a zip built by `sentinel release` from a
clean tree (`dist/`, not committed); none is tagged by the tooling. Research results are
identical across all releases (`sentinel reproduce --check`: 117 of 117 files).

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
- An AI explanation shows action labels in words and tasks by name, says that the AI writes in
  English, can be asked again after an invalid answer and no longer holds up the project.
- README with the application first; user guides, deploy guide, `RELEASE.md` and this
  changelog for 1.3.0.

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
