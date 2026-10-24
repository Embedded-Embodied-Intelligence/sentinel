# WP9a — Application back end: live projects, demo simulator, services and HTTP API

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (§1–§6, §10), `docs/spec/architecture.md`
- `docs/notes/WP3a.md` (beliefs, `state_from_observation`), `docs/notes/WP4a.md` (planning view,
  operations), `docs/notes/WP5a.md` and `docs/notes/WP5b.md` (Sentinel, decision record, gate),
  `docs/notes/WP6b.md` (interpretation layer), `docs/notes/WP8.md` (cockpit)
- skills `spec-guard`, `adr`, `wp-report`

The course goal is *AI-driven project management that is not "Jira with a chatbot"*, used by
business people who will never open a terminal. All research work is done; WP9 turns the engine
into a **simple web application** for a project manager. Owner decisions (binding):
- local web app, open source (MIT), free to run; FastAPI + server-rendered HTML + HTMX (WP9b),
  SQLite from the standard library; runs with `sentinel ui` on a laptop or with Docker on a
  company server; LLM optional (none / local Ollama / Groq free / OpenRouter);
- two modes: **Project** (a real project the manager updates at check-ins) and **Simulator**
  (a generated project with a hidden world, "advance N days", Sentinel vs. no reaction);
- the public demo for the course runs on the owner's server behind Tailscale Funnel
  (HTTPS URL), so a **demo mode** with per-visitor sandboxes and limits is needed.

WP9a builds everything except the pages: the domain mapping, storage, services and a JSON/HTML-
fragment-ready API with tests. WP9b builds the UI, WP9c packaging, deployment and user guide.
</context>

<task>
0. **Spec v2.0** (commit `spec: live project mode and application services (v2.0)`): new §11
   **Live project mode**, binding:
   - Calendar: a project has a start date; model day `t` = working days (Mon–Fri) since the start;
     every date shown to users is a calendar date.
   - Team: people with a display name and a role; role names are free text (any number of roles);
     capacity per role = number of people. Daily cost per role (default 1.0, a "cost unit").
   - Tasks: name, estimated duration (working days), crew per role, predecessors, optional flag
     (may be descoped). Estimation-uncertainty preset per project: `confident` (0.9, 1, 1.3),
     `typical` (0.8, 1, 1.6, the research default), `uncertain` (0.7, 1, 2.0). Disruption-rate
     preset: `calm` (λ_A 0.005), `typical` (0.01), `turbulent` (0.02); λ_S 0.01, λ_N 0.02, E[L] 3;
     editable in advanced settings.
   - Deadline as a date, budget in cost units (default from §1.2 with β = 0.1).
   - **Check-in** at day `t`: per task one of not started / in progress with % done / done with a
     finish date; reported absences (person, first day, announced return date, never a reason);
     reported work increases (task, +N days or ×F); new tasks (fields as above, after/before).
     Mapping to the `Observation`: started tasks have their start day; work done
     `e_j = %done · p_j · ΠF` in full-crew days; a "+N days" report becomes the factor
     `F = (remaining + N) / remaining`; crews are assigned automatically at start by the §3.1 (b)
     rule unless the manager overrides them; absences set presence and the announced bound.
   - Recommendations are Sentinel deliberations on that observation (rule candidates; LLM
     proposals off by default); approving an action applies its operations to the live state
     (new plan, named substitutes, temporary workers "Temporary <role> 1…", removed optional
     task); rejecting records the rejection. The autonomy level Λ is a project setting; actions
     below Λ are applied automatically and listed as such.
   - Simulator mode: a project generated from a PSPLIB instance with IT role and task names (the
     WP6 narrator vocabulary), a hidden world from a seed, `advance(days)` under a chosen policy,
     and a side-by-side comparison with NoReaction on the same seed.
1. **Domain and storage** `src/sentinel/app/`: pydantic models for live projects (team, tasks,
   settings, check-ins, decisions); `store.py` with SQLite (stdlib `sqlite3`): projects, an
   append-only event log (check-ins, decisions, imports) from which the live state is rebuilt
   deterministically, and per-session ownership; schema migrations by version number.
2. **Mapping** `src/sentinel/app/live.py`: live project → `ProjectInstance` (roles, workers,
   activities, source/sink), plan, and `Observation` at day `t`; round-trip tests; validation
   messages for users (missing predecessors, cycles listed by task name, crew above team size,
   deadline before the critical path) in plain language, PL and EN message catalogues.
3. **Services** `src/sentinel/app/services.py` (no HTTP inside): create/import (CSV template with
   documented columns; JSON export/import of a whole project), extract tasks from text (WP6
   extraction, LLM optional, the user reviews the result before it is saved), build baseline
   plan (CP-SAT, `T_cp`, SGS fallback), forecast (WP3: P(on time), P10/P50/P90 finish dates,
   top risk drivers = tasks most often on the critical path in rollouts), check-in, recommend
   (Sentinel decision record → a user-facing recommendation: title in plain language, impact on
   on-time chance / expected finish date / cost / plan changes, alternatives, template
   explanation; LLM explanation optional with the faithfulness badge), decide (approve /
   reject / later), simulator (create, advance, compare), exports (plan CSV, cockpit HTML of
   WP8 for live and simulator projects). Long operations run in a background worker with a job
   id and progress; results are deterministic for a fixed seed.
4. **HTTP API** `src/sentinel/app/api.py` (FastAPI): JSON endpoints for every service, typed
   request/response models, consistent error format with user-readable messages; settings
   endpoint for the LLM provider (keys stored server-side in a settings file outside the
   repository, never returned); health endpoint. `sentinel ui [--host --port --data-dir
   --demo]` starts uvicorn, binding to 127.0.0.1 by default.
5. **Demo mode** (`--demo`): each visitor gets an anonymous session sandbox (signed cookie);
   limits (projects per session, tasks per project, simulator days, concurrent jobs, request
   rate per IP) from config; sandboxes expire after 24 h; a seeded showcase project per session;
   LLM features use the server's configured provider with a daily cap or are disabled; no
   endpoint reveals settings, files or other sessions. CSRF protection for state-changing
   requests.
6. **Dependencies** (ADR): add `fastapi`, `uvicorn`, `jinja2`, `python-multipart` (runtime) and
   `httpx` (dev, for the test client); nothing else. Keep the research code free of web imports
   (import-isolation test: `simulation/`, `agent/`, `policies/`, `forecasting/` never import
   `app/`).
7. **Tests**: live mapping round trips; check-in → observation on hand-made cases (partial
   progress, absence with return date, +N days, new task); a recommendation on a constructed
   project equals the Sentinel decision on the equivalent observation; approve/reject change the
   state as specified and are logged; event-log replay rebuilds the same state; CSV/JSON import
   errors are reported per row in PL and EN; demo isolation (one session cannot read another's
   project), limits and CSRF; API contract tests with the test client; simulator advance is
   deterministic per seed and matches `simulate` for the same policy and seed.
8. Fix the LICENSE copyright holder to "Kamil Piejko" (separate commit).
9. `wp-report` (`docs/reports/WP9a.md`, `docs/notes/WP9a.md` with the API list and the live
   mapping), roadmap row `WP9: in progress: WP9a done`. ADRs: web stack, storage/event log,
   demo-mode security.
</task>

<constraints>
- No UI pages yet beyond a JSON health check (WP9b). No change to research results or semantics
  of §1–§10; `reproduce --check` must still pass.
- Secrets: LLM keys only server-side, never logged or returned. No new dependencies beyond
  task 6. Default `pytest -q` ≤ 75 s (mark slow ones). Commit after each step group.
</constraints>

<acceptance_criteria>
1. Spec v2.0 commit; ADRs; LICENSE commit.
2. Quality gate, `-m "data or slow"` and `sentinel reproduce --check` pass; task-7 tests exist.
3. `sentinel ui` starts and serves the API; `sentinel ui --demo` enforces isolation and limits.
4. Report (with the API list), notes, roadmap; pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP9a.md` via `wp-report`. "Numbers": latency of plan, forecast, recommend and
advance(10 days) on a 30-task and a 60-task project.
</report_format>
