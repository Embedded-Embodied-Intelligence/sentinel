# WP9a report — Application back end: live projects, simulator, services and HTTP API

- Date: 2026-10-24
- Commit(s): 0197c81 (spec v2.0), 10ccda9 (spec §11.5), 5569790 (LICENSE), 6040734
  (dependencies, ADR-0022), 663d540 (domain, mapping, event log), 5e5d7c9 (services, simulator,
  cockpits), e656441 (API, demo mode, `sentinel ui`), 6491be2 (caches, crew history, no docs page,
  benchmark); the report commit follows them

## Summary
Spec v2.0 adds §11 *live project mode*: calendar dates, team, tasks and presets of a real
project, its baseline plan, check-ins mapped onto the `Observation`, forecasts with risk
drivers, recommendations as Sentinel deliberations with the autonomy level, and the simulator
mode. `sentinel.app` implements it without touching §1–§10: a SQLite store whose projects are
append-only event logs, services for live and simulator projects (CSV/JSON import and export,
optional LLM extraction, explanations and proposals, WP8 cockpits), background jobs, a FastAPI
JSON API and `sentinel ui [--demo]`, whose demo mode gives every visitor an isolated sandbox
with limits and CSRF protection. No UI pages yet (WP9b).

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v2.0 commit; ADRs; LICENSE commit | `git show --stat 0197c81 10ccda9 5569790`; `ls docs/adr` | PASS (0197c81 `spec: live project mode and application services (v2.0)`: §11 and the architecture; 10ccda9 clarifies §11.5; ADR-0022 web stack, ADR-0023 SQLite event log, ADR-0024 demo-mode security; 5569790 LICENSE "Copyright (c) 2026 Kamil Piejko") |
| 2 | Quality gate, `-m "data or slow"` and `sentinel reproduce --check` pass; task-7 tests exist | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"`; `uv run sentinel reproduce --check` | PASS (ruff clean, 313 files formatted, mypy: no issues in 124 source files; `pytest -q`: 452 passed, 23 deselected in 74.6 s; `-m "data or slow"`: 37 passed, 438 deselected in 535.4 s (WP8: 25 in 493.6 s); reproduce: 117 of 117 files identical. Task-7 tests: mapping round trips and the hand-written observation (`test_app_live`), check-in cases with partial progress, absence and return date, +N days, new task, crews and errors (`test_app_live`), recommendation = `Sentinel.deliberate` on the equivalent observation, approve/reject/automatic with the log and its replay (`test_app_live`, `test_app_api`), CSV per-row and JSON errors in Polish and English (`test_app_io`, `test_app_api`), demo isolation, forged cookies, CSRF, limits, rate and expiry (`test_app_api`, `test_app_store`), API contract tests (`test_app_api`, 11), simulator advance = `simulate` for Sentinel, NoReaction and baselines, deterministic in any steps (`test_app_simulator`, tiny fixture and j301_1)) |
| 3 | `sentinel ui` starts and serves the API; `sentinel ui --demo` enforces isolation and limits | `uv run sentinel ui --data-dir … --port 8765`; `uv run sentinel ui --demo --config <demo config without secure cookies> --data-dir … --port 8766`; curl | PASS (local: binds 127.0.0.1, `/api/health` ok, create → plan job → check-in → background recommendation, read back in Polish; demo: two visitors each with the showcase, the other's project 404 on read and delete, foreign CSRF token 403, settings 403, docs 404, sixth project 429 `limit_projects`, simulator advance(61) 429 `limit_days`, advance(10) job done; no error in the server log) |
| 4 | Report (with the API list), notes, roadmap; pushed; clean tree | `git push`; `git status --short` | PASS (this report with the API list under Changes, `docs/notes/WP9a.md` with the API list and the live mapping, roadmap row `WP9: in progress: WP9a done`; pushed, clean tree) |

## Changes
- `docs/spec/model.md` — v2.0: §11.1 calendar, §11.2 team, tasks, presets, validation and
  structure, §11.3 baseline plan and check-ins with the mapping to the observation, §11.4
  forecasts and risk drivers, §11.5 recommendations and decisions, §11.6 simulator mode.
- `docs/spec/architecture.md` — the `app/` package, import rules, data directory, application.
- `docs/adr/0022-web-stack.md`, `0023-sqlite-event-log.md`, `0024-demo-mode-security.md`.
- `LICENSE` — copyright holder Kamil Piejko.
- `pyproject.toml`, `uv.lock` — fastapi, uvicorn, jinja2, python-multipart; httpx (dev); a
  pytest filter for Starlette's httpx deprecation warning.
- `src/sentinel/app/calendar.py` — working-day calendar (§11.1).
- `src/sentinel/app/models.py` — definition, presets, settings, check-in reports.
- `src/sentinel/app/live.py` — validation with plain-language issues, `build_model`
  (definition → `ProjectInstance`, costs, D, B), `LiveProject` (tracking state, `observation()`,
  `resolve_checkin`, `resolve_action` through `rehearse`, crew history).
- `src/sentinel/app/messages.py` — English and Polish catalogue of every issue, error, action,
  status and cockpit label.
- `src/sentinel/app/planning.py` — baseline plan (CP-SAT `T_cp`, SGS-LFT fallback, checked),
  forecast with the critical chain, recommendation with impacts, approval.
- `src/sentinel/app/events.py` — event payloads and the replay into a live state.
- `src/sentinel/app/store.py` — SQLite schema v1 (sessions, projects, events, jobs, usage),
  append-only trigger, ownership by session, expiry, migrations by `user_version`.
- `src/sentinel/app/services.py` — the services (no HTTP), caches, per-project locks, limits.
- `src/sentinel/app/jobs.py` — background jobs with progress (threads; inline in tests).
- `src/sentinel/app/io.py` — CSV templates and parsing with per-row issues, JSON export and
  import, plan CSV.
- `src/sentinel/app/llm.py` — provider settings in `settings.json` (0600, key never returned),
  client factory with a cache without prompts, daily cap, extraction, explanations, proposals.
- `src/sentinel/app/simulator.py` — simulator spec, world, day-by-day runs equal to `simulate`,
  views.
- `src/sentinel/app/views.py` — display-ready response models (dates, names, plain texts).
- `src/sentinel/app/cockpit.py` — WP8 cockpit of a finished simulator project; live cockpit
  with the WP8 charts, names and dates.
- `src/sentinel/app/showcase.py` — the demo's showcase project (built once per server).
- `src/sentinel/app/security.py` — signed session cookies, CSRF tokens, rate limiter.
- `src/sentinel/app/api.py` — FastAPI app, guard middleware, error format, 29 endpoints.
- `src/sentinel/app/config.py`, `configs/app_demo.toml` — app settings and demo limits.
- **API** (`/api`, 29 endpoints; jobs answer 202 and are polled at `GET /api/jobs/{id}`):

  | Method and path | Purpose |
  | --- | --- |
  | `GET health` | status, version, demo flag (no session needed) |
  | `GET session` | demo or local, CSRF token, limits, LLM availability, sandbox lifetime |
  | `GET`, `PUT settings/llm` | provider, model, Ollama host, `has_key` (never the key); 403 in the demo |
  | `GET`, `POST projects` | list; create a live project (201) |
  | `POST projects/validate` | the issues of a definition in plain language |
  | `GET`, `DELETE projects/{id}` | a live or simulator project's view; delete (204) |
  | `PUT projects/{id}/definition` | edit (structure frozen once tracking started) |
  | `GET projects/{id}/events` | the event log (sequence, type, time) |
  | `POST projects/{id}/plan`, `…/forecast`, `…/recommendations` | jobs: baseline plan, forecast, recommendation |
  | `POST projects/{id}/checkins` | apply a check-in; returns the project and the recommendation job |
  | `POST projects/{id}/recommendations/{seq}/decision` | approve, reject or later |
  | `POST projects/{id}/recommendations/{seq}/explanation` | LLM explanation with its badge (job) |
  | `GET projects/{id}/export.json`, `…/plan.csv` | the whole project; the plan with progress |
  | `POST projects/{id}/cockpit`, `GET jobs/{id}/cockpit.html` | cockpit page (job, then the page) |
  | `POST projects/{id}/advance` | simulator: advance n days (job with progress) |
  | `POST import/csv`, `POST import/json` | imports (multipart), per-row messages |
  | `GET templates/tasks.csv`, `…/team.csv` | CSV templates |
  | `POST extract` | tasks and team from a text by the LLM (job; draft for review) |
  | `GET simulator/instances`, `POST simulator` | PSPLIB instances; create a simulator project (job) |
  | `GET jobs/{id}` | job state, progress, result or error |

- `src/sentinel/cli.py` — `sentinel ui [--host --port --data-dir --demo --config]`.
- `src/sentinel/interpret/explain.py`, `describe.py` — optional role names for a live project's
  records and state summaries (research calls unchanged).
- `tests/test_app_live.py`, `test_app_store.py`, `test_app_io.py`, `test_app_api.py`,
  `test_app_simulator.py`, `test_app_isolation.py`, `app_cases.py`; `tests/test_llm.py` (the
  app may import the LLM layer).
- `scripts/bench_app.py` — latency of the main operations (Numbers).
- `README.md` (Application), `docs/notes/WP9a.md`, `docs/roadmap.md`.

## Decisions
- **Calendar convention (§11.1).** A check-in reports the end of its date, so it is the
  observation of day `last(d) + 1`; a deadline date is inclusive (`D = last(d_D) + 1`); finishes
  and makespans are shown as the date of their last day of work. This lets a manager report a
  task finished today and keeps `C ≤ D` equal to "finish date not after the deadline".
- **Structure frozen at the first check-in (§11.2).** Team, tasks, estimates, crews and
  dependencies change only until tracking starts; later changes arrive as check-ins (new
  tasks, more work) and actions. Names, deadline, budget, role costs and settings stay editable.
- **Resolved events (ADR-0023).** Check-ins and actions are stored with what they resolved to
  (starts, crews, crew-member days, factors; new plan, crews, temporary workers, handovers), so
  replay needs no solver and no rollout and survives library updates.
- **Actions through the engine.** Approved and automatic actions run through `rehearse` on the
  current observation and the state it leaves is mapped back; approval first calls the agent's
  own `approve` (operations re-validated, plan part re-planned), so §4 holds by construction.
- **Recommendation = `Sentinel.deliberate`.** A fresh agent per recommendation, spec §8
  parameters, `Λ` from the project, DESCOPE if unstarted optional tasks remain; the test
  compares it with a deliberation on a hand-written observation. The figures shown are the
  record's (spec §11.5 clarified: NOOP may have only `N₁ = 25` rollouts when racing dropped it);
  mean makespans re-run the same rollouts and are checked against the record's `p̂`.
- **Baseline plan** with CP-SAT `T_cp = 0.1` (seed 0, one worker, as the policies) and the
  SGS-LFT fallback, checked by `validate_schedule`. Simulator projects use the studies' cached
  `cpsat_det` plan (5 deterministic s, seed 2026) so that a simulator world is a study world and
  its cockpit is exactly the WP8 page.
- **Jobs** run on threads (1 locally, 2 in the demo), inline in tests; results go to the `jobs`
  table. Forecasts are not events (they change nothing).
- **LLM features** (extraction, explanations, proposals) are opt-in, use the server's provider
  through a cache without prompts (`store_prompts = false`, real data), count one use per
  feature request against the daily cap, and never block a deliberation (a failed proposal
  call adds nothing). The key lives only in `settings.json` (0600) and is passed as a `Secret`.
- **Cockpits.** A finished simulator project gets the WP8 page itself (world and runs handed to
  its assembly). A live project has one partial execution, not two complete runs, so it gets a
  page built from the WP8 CSS, script and SVG charts with task and people names and dates; the
  realised segments come from the reported starts, finishes, crews (with their history) and
  absences.
- **Showcase.** An eight-person online shop relaunch: two check-ins, the second with an absence,
  extra work and a new task, ending with an open recommendation (Cyrus replaces the absent Ben,
  P(on time) 0.52 → 0.62, finish 18 Dec instead of 22 Dec). Built once per server (1.4 s).
- **Small choices:** role names matched with the WP6 `normalise_role`; temporary workers keyed
  `temp:n` (no person key can collide); error kinds mapped to 422/404/409/429/413/503; SQLite in
  WAL mode with `synchronous = NORMAL`; ids from `secrets.token_urlsafe`.
- ADRs created: ADR-0022 (web stack), ADR-0023 (projects as an event log in SQLite), ADR-0024
  (demo-mode security).

## Deviations
- Nine application tests are marked `slow` although each takes under 2 s: the default suite
  took 72.2 s of its 75 s budget before WP9a. The default run keeps one test per requirement
  (mapping round trips, check-in cases, recommendation = deliberation, approve/reject, replay,
  CSV per-row errors, store isolation and expiry, demo isolation, limits and CSRF, LLM settings,
  simulator = `simulate`); the API flow tests, the LLM features and the J30 simulator runs are
  in `-m "data or slow"`. The marker description in `pyproject.toml` says so.
- `sentinel ui` has a `--config` option besides `--host --port --data-dir --demo`: the demo's
  limits come from `configs/app_demo.toml` (the default with `--demo`).
- No `/api/docs` page (FastAPI's Swagger UI is an HTML page that loads a CDN): the constraint
  allows no UI pages before WP9b; local mode serves the JSON schema at `/api/openapi.json`.
- Task extraction returns the draft definition and the number of issues left after the repair
  rounds; its plain-language issues come from `POST /api/projects/validate` on the draft (the
  WP6 issue texts are English model feedback, not user messages).

## Spec questions
1. **Share done and SUBST onboarding.** With `e_j = x · p_j · ΠF` (binding), the onboarding
   added by an approved SUBST is never consumed by reported progress, so the remaining-work
   estimate keeps it until the task is reported done (conservative by `m_j o_j` crew-member
   days). Reading: as written.
2. **OVERTIME in small teams.** `⌊γ R_k⌋ = 0` for roles with fewer than five people, so live
   projects with small roles never get the OVERTIME candidate (the showcase cannot hire).
   Should live projects allow `max(1, ⌊γ R_k⌋)`? Reading: §4 unchanged.
3. **New tasks start no earlier than `t + 1`** (§3.1 e, §10.2), i.e. two working days after the
   check-in date under NoReaction; a SHIFT can pull them earlier. Reading: as written.
4. **Cost so far** prices the work done at the current crew's daily cost (people only), exact
   for crews without substitutions; temporary workers are paid per hired day (§11.3).
5. **Absences before the project start** begin on day 0 (`absent_since` is a model day ≥ 0);
   `L_low` is counted from day 0.
6. **Corrections.** A check-in cannot un-start a task, undo a finish or change a reported start
   (§11.3); corrections need a later WP (e.g. a correction event that replays the log).

## Numbers
Latency of the main operations (`scripts/bench_app.py`; i5-6600K, WSL2, one process, idle;
three instances per size, the state of a check-in at the end of day 9 with one crew member
absent; every baseline plan found the PSPLIB optimum):

| Operation | 30 tasks: mean / max (s) | 60 tasks: mean / max (s) |
| --- | ---: | ---: |
| baseline plan (CP-SAT, `T_cp` = 0.1, SGS fallback unused) | 0.01 / 0.01 | 0.01 / 0.02 |
| forecast, 200 rollouts with risk drivers | 0.24 / 0.26 | 0.38 / 0.47 |
| recommendation: deliberation (500–600 rollouts) and impacts | 0.72 / 0.97 | 1.21 / 1.34 |
| simulator advance(10), days 0–9 (Sentinel Λ = 2 and NoReaction) | 2.63 / 5.75 | 5.82 / 13.18 |
| simulator advance(10), days 10–19 | 3.49 / 4.97 | 3.34 / 5.12 |

Instances: j301_1, j3010_1, j3020_1 and j601_1, j6010_1, j6020_1. A simulator advance is a job
with progress; an advance with several gated deliberations (j6010_1, days 0–9) takes longest.

| Quantity | Value |
| --- | --- |
| default `pytest -q` | 452 passed, 23 deselected in 74.6 s (without the app tests 72.6 s; 72.2 s before WP9a) |
| app tests in the default run | 27, 1.9 s of test time and 0.26 s of web-stack import |
| `pytest -q -m "data or slow"` | 37 passed, 438 deselected in 535.4 s (WP8: 25 in 493.6 s) |
| `sentinel reproduce --check` | 117 of 117 files identical (40 s) |
| showcase project | built once per server start in 1.4 s (a CP-SAT plan, two deliberations) |
| live cockpit of the showcase | 24 kB, self-contained; a simulator cockpit is the WP8 page |
| a JSON request in the test client | about 5 ms |
| real server, small project (curl) | plan job done within 1 s; check-in answered at once, its recommendation job done within 3 s |
| demo server (curl, two cookie jars) | other visitor's project 404 (read, delete), foreign CSRF token 403, settings 403, `/api/docs` 404, sixth project 429, advance(61) 429 |
| application code | 20 modules in `src/sentinel/app`, 39 tests (27 in the default run) |

## Commands for the owner
Nothing long-running is needed for WP9a. To try the application:

```bash
uv sync                                        # installs the web stack
uv run sentinel ui                             # http://127.0.0.1:8000/api/health; data in ~/.local/share/sentinel
uv run sentinel ui --demo --port 8000          # demo mode with configs/app_demo.toml (in tmux)
uv run python scripts/bench_app.py j30/j301_1 j30/j3010_1 j30/j3020_1 \
  j60/j601_1 j60/j6010_1 j60/j6020_1           # the latency table below, about 1 min
```

The public demo (WP9c will document it): run the demo in tmux on 127.0.0.1:8000 and expose it
with `tailscale funnel 8000`; the demo config sets secure cookies, so it must be served over the
funnel's HTTPS. To use an LLM, set the provider once in local mode (`PUT /api/settings/llm`,
or edit `settings.json` in the data directory, mode 0600) before starting the demo.

## Open issues / next steps
- WP9b: HTMX pages on this API (projects, check-in form, recommendation card with approve /
  reject / later, simulator, settings); WP9c: Docker image, deployment behind Tailscale Funnel,
  user guide (Polish and English).
- Team changes after tracking starts (a new hire, a leaver) and check-in corrections.
- Absences announced for a later date are stored but invisible to forecasts until they begin
  (the model has no announced future absences).
- Spec questions 1 and 2 (onboarding in the share done; OVERTIME for small roles).
- Behind the funnel, the per-address rate limit relies on `X-Forwarded-For`
  (`trust_proxy = true`); if the funnel does not set it, all visitors share one bucket. WP9c
  should check the header on the server.
- The job worker uses threads; rollouts hold the GIL, so two concurrent deliberations share one
  core. A process pool is possible if the demo needs more throughput.
