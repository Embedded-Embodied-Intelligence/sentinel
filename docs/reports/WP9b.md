# WP9b report — The user interface: plain-language project control for business users

- Date: 2026-10-25
- Commit(s): 341bf55 (spec v2.0.1), 7d93be7 (live overtime minimum), ec773c0 (pages,
  ADR-0025), 051579b (end-to-end tests, accessibility scan, screenshot script), fc31f25 (gzip,
  more page tests, review fixes); the report commit adds the screenshots

## Summary
`sentinel ui` now serves pages for project managers in Polish (default) and English, built with
server-rendered Jinja2 templates, vendored HTMX and one CSS file (ADR-0025): the start page, a
three-step wizard with autosave (team pasted as a list; tasks described to the AI, imported from
a spreadsheet or typed in a table), the overview with the chance of meeting the deadline, its
trend, the finish dates, the budget outlook, the threats and a plan-and-progress chart, the
check-in (also from a message read by the AI), the recommendation with its effect, reasons and
alternatives, undo of an automatic plan change, history, settings, the simulator with its
comparison, and "How it works". Spec v2.0.1 answers the WP9a questions and fixes the wording of
every action and term (§11.7); a checker proves that no page shows an internal term.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v2.0.1 commit; ADR; quality gate, `-m "data or slow"`, `-m e2e` and `reproduce --check` pass | `git show --stat 341bf55`; `ls docs/adr`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"`; `uv run pytest -q -m e2e`; `uv run sentinel reproduce --check` | PASS (341bf55 `spec: live overtime minimum and UI wording (v2.0.1)`; ADR-0025 front-end stack; ruff clean, 332 files formatted, mypy: no issues in 133 source files; `pytest -q`: 473 passed, 30 deselected in 81.9 s; `-m "data or slow"`: 38 passed, 465 deselected in 543.5 s; `-m e2e`: 6 passed in 58.5 s; reproduce: 117 of 117 files identical) |
| 2 | All screens in PL and EN; the internal-term checker passes; accessibility scan without serious violations | `uv run pytest -q tests/test_ui_pages.py tests/test_ui_text.py`; `uv run pytest -q -m e2e -k accessibility` | PASS (every screen and state in both languages through the checker: no internal term, missing text, raw code, ISO date or decimal percentage; `test_ui_text` checks both catalogues; axe: no serious or critical violation on 14 screens, light and dark) |
| 3 | Screenshots committed; the report lists them | `ls -la docs/ui` | PASS (six PNGs, 651 kB in total, listed under Numbers) |
| 4 | Report, notes, roadmap; pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP9b.md` with the screen map and the UX rules, roadmap row `WP9: in progress: … WP9b done`; pushed, clean tree) |

## Changes
- `docs/spec/model.md` — v2.0.1: §11.2 temporary workers (`u_min = 1` in live and simulator
  projects), §11.3 onboarding in the share done accepted as slightly pessimistic, §11.5 undo of
  an automatic plan change, §11.6 simulator with `u_min`, §11.7 wording table (PL and EN) and
  the list of terms never shown.
- `src/sentinel/simulation/state.py`, `engine.py`, `agent/candidates.py`,
  `interpret/actions.py`, `interpret/describe.py` — the OVERTIME cap `max(u_min, ⌊γ R_k⌋)`
  with `u_min` reported by the observation (`overtime_floor`, default 0, left out of
  serialisation) and passed to `simulate`; research runs unchanged.
- `src/sentinel/app/models.py` (`OVERTIME_FLOOR = 1`), `live.py`, `simulator.py` — the live and
  simulator observations report `u_min = 1`.
- `src/sentinel/app/views.py` — actions in the §11.7 wording (the absent member a substitute
  replaces, found as SUBST does), why an action needs approval, `can_undo`, temporary people in
  the user's language, the forecast's budget outlook and `ForecastSummary` (trend).
- `src/sentinel/app/events.py` — the `undo` event, the `undone` status, `last_change`,
  `can_undo`.
- `src/sentinel/app/planning.py` — the forecast's mean total cost and share within the budget.
- `src/sentinel/app/services.py` — undo, forecasts cached by project and last change with the
  trend, check-in messages read by the AI (job), AI connection test (job), `with_simulation`.
- `src/sentinel/app/llm.py` — `read_message` (the §10.2 parser on a live project: its roles,
  tasks and team, the manager as author, days shifted to the prompt's Monday numbering),
  `test`.
- `src/sentinel/app/store.py` — `project_jobs`.
- `src/sentinel/app/messages.py` — §11.7 action wording, plain AI errors, undo and reference
  messages, live-cockpit labels without "P(on time)".
- `src/sentinel/app/api.py` — the guard serves sessions, CSRF and the language to the pages;
  HTML error pages with a reference id; `POST …/recommendations/{seq}/undo`,
  `POST …/messages`, `POST settings/llm/test`; gzip.
- `src/sentinel/app/cockpit.py` — the live cockpit uses the new wording.
- `src/sentinel/app/ui/` — new: `core.py` (environment, context, HTMX responses, errors),
  `text.py` (532-key catalogue PL/EN, dates, percentages, plurals), `forms.py` (form reading and
  validation), `charts.py` (plan-and-progress SVG), `pages.py` (start, how it works, settings,
  jobs, language), `setup.py` (wizard), `project.py` (overview, check-in, recommendation,
  history, settings, report, deletion), `sim.py` (simulator), 37 templates, `static/`
  (`sentinel.css`, `sentinel.js`, `htmx-2.0.11.min.js` with its licence, `favicon.svg`).
- `tests/test_ui_text.py`, `test_ui_forms.py`, `test_ui_pages.py`, `test_ui_e2e.py`,
  `ui_check.py`; `tests/vendor/axe-core-4.14.0/` (axe.min.js, licences); updated
  `test_app_live.py`, `test_app_simulator.py`, `test_app_api.py` (u_min, new wording).
- `scripts/ui_screenshots.py`; `docs/ui/*.png`.
- `docs/adr/0025-front-end-stack.md`; `pyproject.toml`, `uv.lock` (dev: `playwright==1.63.0`;
  `e2e` marker, excluded by default; slow marker text); `.pre-commit-config.yaml` (vendored files
  stay byte-identical); `CLAUDE.md`, `docs/workflow/wp-protocol.md` (90 s budget, e2e);
  `README.md` (Application, screenshots); `docs/notes/WP9b.md`; `docs/roadmap.md`.

## Decisions
- **Pages call the services, not the HTTP API** (ADR-0025): the same views, no second client;
  every state change is an HTMX request carrying the session's CSRF header (ADR-0024); the
  guard now serves pages too (Polish unless a cookie chose English) and refuses with an HTML
  message. HTMX's response handling swaps error responses, which the server retargets to the
  page's message area, so a refused form explains itself.
- **A project exists from the end of wizard step 1** as a draft without a plan; later steps save
  on every change (autosave, one `definition` event per change, consecutive edits shown as one
  history entry). The start page lists drafts with "Continue the setup".
- **Forecasts on the overview** are computed when the page asks for them (0.2–0.5 s, loaded
  after the page) and cached per project and last change; the trend compares with the state
  before the latest check-in; the budget outlook uses the same 200 rollouts.
- **Undo** (spec §11.5 v2.0.1): only an automatic action that changed only the plan, while
  nothing but explanations came after it; the `undo` event stores the restored planned starts.
- **"Why"** is composed from the recommendation's own figures and the deciding component in
  words; the WP8 template explanation (with action labels) stays in the detailed report.
- **Check-in messages**: the WP6b parser and prompt are reused with a context built from the
  live project (its role names, task names and team; the author is the project manager); days
  are numbered from a Monday as the prompt requires and shifted back. With
  `store_prompts = false` an answer with one invalid event is withheld whole (spec §10), so
  the repair rounds matter; every event found is shown for confirmation, unticked ones are not
  saved.
- **Simulator examples** are the WP8 cockpit worlds: J30 `j3026_7` and J60 `j6010_7`,
  replication 1, started today.
- **Wording details** beyond the §11.7 table: "No change (keep the plan)" for NOOP among the
  alternatives (the table's "…the plan is still the best" is the wording of a chosen NOOP);
  risk drivers as "on the critical path in 8 of 10 simulated futures"; Polish names are not
  declined ("udział osoby nieobecnej (Ben Kowalski)").
- **Gzip** responses (Starlette's middleware, no new dependency): a first visit transfers about
  25 kB instead of 77 kB.
- ADRs created: ADR-0025 (front-end stack).

## Deviations
- **Chromium's system libraries.** Playwright's Chromium needs `libnss3`, `libnspr4` and
  `libasound2t64`, which are not installed on the server and need root. The e2e tests and the
  screenshots ran in this session with the three Ubuntu packages extracted (`apt-get download`,
  `dpkg-deb -x`, no root) into the session's scratch directory and `LD_LIBRARY_PATH`; the
  owner should install them once (Commands for the owner). Without a browser the e2e tests skip
  with the reason.
- **The detailed report** ("Show the report", project settings) is the WP8 cockpit, a technical
  page with its provenance (parameters and symbols); it is outside the wording rules. Its live
  version's labels are now plain.
- **Message texts** of the API changed with §11.7 (action titles) and the plain AI errors; the
  WP9a API test now expects the new title.
- The 75 s comments of WP9a's slow-marked app tests were left as written; the budget is 90 s.

## Spec questions
1. **Rough "without a change" figure.** §11.5 shows each candidate's figures from its own
   rollouts; when racing sets NOOP aside early, its chance comes from `N₁ = 25` rollouts. On
   the showcase the recommendation shows 52 % without a change while the overview's forecast
   (200 rollouts, §11.4) shows 39 % (1000 rollouts: 40 %). Proposal: extend NOOP's rollouts to
   `N` for the figures shown (as the impacts already re-run rollouts), or show the forecast as
   "without a change". Reading used: as written, with a note on the page that the figure is
   rough.
2. **Trivial risk drivers.** The last task before the sink is on the critical chain of every
   completed rollout (showcase: "Launch" in 10 of 10). Should §11.4 leave out activities whose
   only successor is the sink, or rank by the share of rollouts in which a task delays the
   finish? Reading: as written; the page explains the critical path.
3. **`u_min` in the simulator.** J30 has roles of 3 people, so with `u_min = 1` the app's
   simulator can hire where the studies could not; its runs then differ from the studies' worlds
   (and from `sentinel dashboard`). Reading: as the WP asked (live and simulator modes).

## Numbers
Environment: i5-6600K, WSL2, idle unless noted; Chromium 153.0.8010.12 (Playwright 1.63.0
headless shell) with `libnss3`, `libnspr4` and `libasound2t64` extracted locally (Deviations).

| Quantity | Value |
| --- | --- |
| default `pytest -q` | 473 passed, 30 deselected in 81.9 s (budget 90 s; 452 in 75.3 s before the pages) |
| UI tests in the default run | `test_ui_text` 6, `test_ui_forms` 5, `test_ui_pages` 10 (about 8 s with the projects they build) |
| `pytest -q -m "data or slow"` | 38 passed, 465 deselected in 543.5 s (WP9a: 37 in 535.4 s; new: the simulator pages, 7 s) |
| `pytest -q -m e2e` | 6 passed in 58.5 s: simulator to the end 38.6 s, axe light 6.3 s and dark 4.8 s (14 screens each), spreadsheet to approval 4.6 s, demo isolation 1.0 s, keyboard check-in 1.0 s |
| `sentinel reproduce --check` | 117 of 117 files identical (40.5 s) |
| accessibility (axe-core 4.14.0) | 0 serious or critical violations on 14 screens in light and dark mode; 37–44 rules passed per screen; left for review: decorative symbols and SVG tick labels (contrast checked by hand: ≥ 6:1) |
| catalogue | 532 keys in English and Polish, the same placeholders; 37 templates; `sentinel.app.ui` 3,899 lines of Python |
| screenshots `docs/ui/` (PL, 1280×800) | `pl_start.png` 113 kB, `pl_wizard_tasks.png` 97 kB, `pl_overview.png` 129 kB, `pl_checkin.png` 82 kB, `pl_recommendation.png` 152 kB, `pl_simulator_comparison.png` 95 kB; total 651 kB (limit 3 MB) |
| AI flows with a scripted model | description → 2 tasks, a check-in message → 1 absence to confirm, connection test; real models not called |

Page weights (the showcase project; HTML as served, and as transferred with gzip; the static files
are loaded once and cached):

| Page | HTML (kB) | gzip (kB) |
| --- | ---: | ---: |
| start | 3.5 | 1.5 |
| new project, step 1 | 5.5 | 2.0 |
| new project, step 3 (12 tasks) | 26.4 | 3.9 |
| overview (with its chart) | 15.8 | 3.8 |
| forecast block (loaded after) | 1.3 | 0.7 |
| check-in | 26.4 | 4.1 |
| recommendation | 6.8 | 2.4 |
| history | 5.2 | 1.8 |
| project settings | 7.9 | 2.6 |
| simulator | 4.5 | 1.7 |
| how it works | 4.5 | 2.1 |
| `sentinel.css` | 21.0 | 5.3 |
| `sentinel.js` | 1.8 | 0.7 |
| `htmx-2.0.11.min.js` | 51.0 | 16.5 |

A first visit loads about 77 kB (25 kB transferred); every later page 2–4 kB transferred. The
overview's forecast takes 0.2–0.5 s and is cached until the project changes; the simulator's small
example runs to the end in about 33 s on one worker thread.

## Commands for the owner
```bash
uv sync                                                 # Playwright (dev) and its deps
uv run playwright install chromium                      # once: Chromium for Playwright
sudo apt-get install -y libnss3 libnspr4 libasound2t64  # once: Chromium's system libraries
uv run pytest -q -m e2e                                 # about a minute
uv run sentinel ui                                      # http://127.0.0.1:8000 (Polish; EN top right)
uv run python scripts/ui_screenshots.py                 # docs/ui/*.png again, about a minute
```

## Open issues / next steps
- WP9c: Docker image, deployment behind Tailscale Funnel, the user guide (Polish and English;
  "the estimate improves when the task is marked done", spec §11.3).
- Spec questions 1–3.
- Team changes after tracking starts and check-in corrections (WP9a) are still not in the UI.
- The task table of the wizard grows wide with many roles; a role-per-row editor may suit teams
  with more than five roles.
- Rate limit in the demo: a long simulator run polls once a second (60 requests per minute of
  the 120 allowed).
- `docs/spec/architecture.md` does not list `app/ui/` yet (the WP did not ask to edit
  `docs/spec/`); ADR-0025 and the notes describe the package.
