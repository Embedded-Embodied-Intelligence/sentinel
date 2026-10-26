# WP9c report — UI fixes, Docker, public demo, user guide and usability protocol

- Date: 2026-10-26
- Commit(s): dd0d91d (spec v2.0.2), 6ca8fc3 (the four fixes), 75825e0 (e2e libraries without
  root), f5dee10 (Docker, demo, ADR-0026), a2ead20 (spec: threat sentence), 889c1e8
  (screenshots), 9eb2186 (user guides, usability), c485ec9 (version 1.1.0); the report commit
  adds this report, the notes and the roadmap

## Summary
Spec v2.0.2 answers the WP9b questions and the application follows it: every figure shown with
a recommendation (the optional AI text aside, spec question 3) comes from one comparison on the
overview forecast's 200 simulated futures, so "no change" equals the overview's chance
(showcase: 39 % on both pages); "What threatens the
deadline" counts tasks over the late futures without structural, zero-duration and finished
tasks; costs read "27 z 84 jednostek kosztu (osobodni)" and "+2 jedn., +2 % budżetu"; the
example projects are named in the user's language; the simulator says it uses the
application's settings. The app is packaged as a two-stage uv image with compose and an optional Ollama
profile (ADR-0026), the public demo runs behind Tailscale Funnel with per-visitor limits that
trust `X-Forwarded-For` only from 127.0.0.1, user guides exist in Polish and English, and a
usability protocol with a scripted task-timing baseline is ready for the owner.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v2.0.2 commit; ADR; quality gate, `-m "data or slow"`, `-m e2e` and `reproduce --check` pass | `git show --stat dd0d91d`; `ls docs/adr`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"`; `uv run pytest -q -m e2e`; `uv run sentinel reproduce --check` | PASS (dd0d91d `spec: display comparison, threats, wording (v2.0.2)`, with a2ead20 for the threat sentence; ADR-0026 Docker image and public demo; ruff clean, 345 files formatted, mypy: no issues in 134 source files; `pytest -q`: 490 passed, 31 deselected in 83.8 s; `-m "data or slow"`: 38 passed, 483 deselected in 538.9 s; `-m e2e`: 7 passed in 93.4 s; reproduce: 117 of 117 files identical) |
| 2 | The four fixes are visible on regenerated screenshots | `uv run python scripts/ui_screenshots.py --lang pl` (and `--lang en`); `ls docs/ui` | PASS (22 PNGs, 11 per language: the overview's 39 % and the chip "39 % → 55 %" (`pl_overview.png`, `pl_recommendation.png`); the threats "Zadanie „Testy integracyjne” decyduje o terminie w 7 na 10 scenariuszy z opóźnieniem" without the first and last tasks (`pl_overview_threats.png`); the simulator's note on the application's settings (`pl_simulator.png`, `pl_simulator_comparison.png`); "27 z 84 jednostek kosztu (osobodni)", "+2 jedn., +2 % budżetu", "92 jedn." and Polish names throughout) |
| 3 | Docker files, deploy guide and demo script; user guides PL/EN; usability protocol and template; task-timing baseline in the report | `ls Dockerfile docker-compose.yml .dockerignore docs/deploy.md scripts/run_demo.sh docs/user-guide-*.md docs/usability/`; `uv run pytest -q tests/test_app_deploy.py tests/test_docs_links.py`; `SENTINEL_TASK_TIMING=docs/usability/baseline-timing.json uv run pytest -q -m e2e -k usability` | PASS (the files exist; the compose file parses and the Dockerfile has its three stages, non-root user, volume and health check; every link and image of the guides exists; baseline under Numbers). Docker is not installed on this server, so the image was not built: its recipe was replayed without Docker (Deviations) and the build commands are below |
| 4 | `dist/sentinel-1.1.0.zip` built; report, roadmap; pushed; clean tree | `git status --short`; `uv run sentinel release --version 1.1.0`; `git push` | PASS (19.9 MB, 623 files of commit c485ec9, byte-identical on a second build, no `data/`, no `.env` but `.env.example`; not tagged; rebuilt from the report commit afterwards, which `dist/` holds; report, notes, roadmap `WP9: done`; pushed; clean tree) |

## Changes
- `docs/spec/model.md` — v2.0.2: §11.2 costs shown in cost units, §11.4 threats over the late
  rollouts (structural, zero-duration and finished tasks left out), §11.5 one comparison on the
  forecast's worlds, §11.6 the simulator's settings note and the names per language, §11.7 cost
  and threat wording; `docs/spec/architecture.md` — `app/`, `app/ui/`, deployment options.
- `src/sentinel/app/planning.py` — `Comparison`, `compare`, `shown_labels`; threats
  (`threat_candidates`, `structural`, `ForecastResult.late`); the deliberation's own impacts are
  no longer recomputed (`Recommendation.impacts` kept for logs before v2.0.2).
- `src/sentinel/app/views.py` — outcomes and alternatives from the comparison (old logs as
  before), `compared`, `options`, `budget`, `runner_up`, `person_days`, `ForecastView.late`;
  `cockpit.py` — the detailed report uses the comparison's worlds; `live.py` — `Node` public.
- `src/sentinel/app/names.py`, `app/vocabulary/en.toml`, `pl.toml` (new) — names of the
  showcase and the simulator per language; `showcase.py` — built per language, copied into a
  sandbox in the visitor's language, the Polish one computed at start-up; `simulator.py`,
  `ui/sim.py`, `services.py` — simulator names in the page's language; `messages.py` —
  `temporary_role`.
- `src/sentinel/wbs/narrate.py`, `interpret/team.py` — optional `vocabulary` and `first_names`
  parameters of the name generators (defaults unchanged: research outputs identical).
- `src/sentinel/app/ui/text.py` — threats, comparison and cost-unit texts, `Texts.cost`,
  `cost_of`, `cost_short`, `cost_change`, `tenths`; templates `_forecast.html`,
  `recommendation.html`, `_rec_card.html` (the rough-figure note removed), `simulation.html`,
  `simulator.html`, `project_settings.html`; `sentinel.css` (`.unit`).
- `src/sentinel/app/security.py` — `client_address` (X-Forwarded-For only from 127.0.0.1, the
  last hop the proxy added); `api.py` — the guard uses it, `/api/client-address` (local only),
  the sandbox's showcase in the request's language; `cli.py` — uvicorn without proxy headers.
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `configs/app_server.toml` (new);
  `configs/app_demo.toml` (comment); `docs/adr/0026-docker-image-and-public-demo.md`.
- `scripts/run_demo.sh`, `scripts/setup_e2e_libs.sh` (new); `scripts/ui_screenshots.py` (both
  languages, 11 screens, scroll targets, Chromium's libraries).
- `docs/deploy.md`, `docs/user-guide-pl.md`, `docs/user-guide-en.md`, `docs/usability/`
  (protocol, results template, test project CSV and team, `baseline-timing.json`), `docs/ui/`
  (22 PNGs), `README.md` (links), `docs/notes/WP9c.md`, `docs/roadmap.md`.
- `src/sentinel/release.py` — RELEASE.md describes the application, Docker and the guides;
  `pyproject.toml`, `uv.lock` — version 1.1.0.
- Tests: `test_app_display.py`, `test_app_deploy.py`, `test_docs_links.py` (new, default run),
  `test_ui_usability.py` (new, e2e), `e2e_env.py` (new helper: server, Chromium's environment);
  updated `test_ui_pages.py`, `test_ui_text.py`, `test_app_live.py`, `test_app_simulator.py`,
  `test_ui_e2e.py`, `test_release.py`, `test_app_api.py`.

## Decisions
- **The comparison is stored with the recommendation** (its seed, 200 rollouts and the figures
  of the choice, at most five alternatives and NOOP), computed once in the recommendation job
  (about 0.3 s on the showcase), so replaying the log runs no rollout (ADR-0023). The page lists
  the choice, the runner-up, then the other alternatives by their own chance; the "set aside
  early" label of racing is no longer shown with these figures.
- **Threats**: the share is counted over the completed late rollouts; a share rounds to tenths
  half up, "in nearly every" for 0.95–0.99; truncated rollouts (no finish) are not counted.
- **Cost units**: the meaning "(osobodni)" / "(person-days)" is shown only while every daily
  cost is the default 1; Polish plurals by the rounded number ("84 jednostki", "27 z 84
  jednostek"); changes below 1 % of the budget read "poniżej 1 % budżetu".
- **Names**: one vocabulary file per language; the English file holds the narrator's own
  lists (a test checks equality), so English simulator names are the studies'; the Polish lists
  have the same lengths, so the same seed gives the translation. Simulator names follow the
  page's language; the showcase is data, copied in the language of the visitor's first request.
- **Client address**: the app trusts `X-Forwarded-For` only from 127.0.0.1 and takes the last
  hop that is not the proxy; uvicorn's own proxy-header rewriting is off so the app sees the TCP
  peer; `/api/client-address` answers only requests from 127.0.0.1, which includes the funnel's
  (it shows a visitor only their own address).
- **Docker**: uv 0.13.2 (the server's) in the build stage, `python:3.12-slim`, uid 10001,
  `/data` volume, configs and the PSPLIB downloader in the image (PSPLIB itself only in the
  volume, invariant 5), compose bound to 127.0.0.1:8000, Ollama 0.40.6 (the studies' version)
  in an optional profile with `OLLAMA_HOST` preset.
- **Demo**: its own data directory (`~/.local/share/sentinel-demo`), tmux by default, a user
  systemd unit on request; `funnel`/`unfunnel` are commands for the owner (`tailscale funnel
  --bg`, `tailscale funnel reset`).
- **E2E libraries without root** (the owner's request during the WP): `apt-get download` and
  `dpkg -x` into `~/.local/share/sentinel-e2e-libs`, prepended to Chromium's `LD_LIBRARY_PATH`
  by the tests and the screenshot script; the downloaded packages are kept, nothing is deleted.
- **Usability test project**: seven tasks, five people; checked that the absence of the scenario
  leads to a substitution waiting for approval for deadlines from 27 Nov to 4 Dec (4 Dec used:
  75 % before, 46 % after the absence).
- ADRs created: ADR-0026 (Docker image and public demo).

## Deviations
- **Docker was not built**: it is not installed on the server (`docker: command not found`),
  as the owner allowed. The recipe was checked by replaying it: a non-editable `uv sync` of the
  build context into a fresh environment (270 MB, templates, static files and vocabularies
  included), started with `configs/app_server.toml`: healthy after 3.7 s, a project created and
  planned through the API, the Polish start page served, `X-Forwarded-For` ignored outside the
  demo. Image size and start time: Commands for the owner.
- **The funnel was not started** (as the WP asked). `scripts/run_demo.sh start`/`check`/`stop`
  ran locally on port 8791: the check from the local proxy saw 203.0.113.7, the first visit got
  the Polish showcase in 0.15 s, `tailscale funnel status` stayed "No serve config".
- **Recommendations stored before v2.0.2** keep their old figures (no comparison, the old texts
  and the "set aside early" label); new ones carry the comparison. No migration: demo sandboxes
  expire within a day.
- **The simulator's detailed report** (the WP8 cockpit, a technical page) still names tasks
  with the narrator's English words in Polish.
- **Task 3 of the protocol** ("report an absence") is a whole check-in (the workshop done, the
  API in progress, the absence), so that task 4 has a recommendation to decide on.
- **README** links the guides and the e2e library script (the WP did not list it).

## Spec questions
1. **Structural tasks and optional tasks.** With every path counted, the optional gift cards of
   the showcase give a path that avoids the launch, so only the first task would be structural
   and "Launch" would again head the list ("in 9 of 10 late scenarios", share 0.93). Reading used:
   paths of the required tasks (optional and dropped tasks left out); showcase: the first task,
   the performance tests and the launch are left out. Written so in v2.0.2 §11.4.
2. **Finished tasks among the threats.** The critical chain of a late rollout runs back through
   tasks already done, which nothing can change any more: in the showcase, "Requirements
   workshop" (done on 3 Nov) is on the chain of 7 in 10 late futures. It is also structural, so
   it is left out either way there, but a finished task that is not structural would be listed.
   Reading used: done and dropped tasks are left out, with the zero-duration ones.
3. **The AI explanation on a recommendation page** (optional, §10.4) explains the decision
   record, whose figures are the deliberation's own (racing), not the comparison's, so its
   numbers can differ from the page's. Should the application pass the comparison's figures to
   §10.4 (a change of what is explained), or label the AI text as an explanation of the decision?
   Reading: as written (§10.4 unchanged).
4. **The comparison can rank an alternative above the choice** (another 200 worlds than
   racing's). The page then shows the choice with a lower chance than an alternative and the
   deciding component in words; accepted by answer 1 ("the decision stands"), noted for the
   paper.

## Numbers
Environment: i5-6600K, WSL2, idle unless noted; Chromium for Playwright 1.63.0 with the
libraries of `scripts/setup_e2e_libs.sh`.

| Quantity | Value |
| --- | --- |
| default `pytest -q` | 490 passed, 31 deselected in 83.8 s (budget 90 s; WP9b: 473 in 81.9 s) |
| `pytest -q -m "data or slow"` | 38 passed, 483 deselected in 538.9 s (WP9b: 38 in 543.5 s) |
| `pytest -q -m e2e` | 7 passed in 93.4 s: simulator to the end 37.4 s, the usability tasks 34.9 s, axe light 6.7 s and dark 4.8 s (14 screens each, no serious or critical violation), spreadsheet to approval 4.8 s, demo isolation 1.0 s, keyboard check-in 0.9 s |
| `sentinel reproduce --check` | 117 of 117 files identical (40.5 s) |
| new default tests | `test_app_display` 4 (0.6 s), `test_app_deploy` 5 (0.3 s), `test_docs_links` 6 (0.03 s), page test 2 |
| showcase (Polish) | overview 39 % = "no change" 39 %; with the substitution 55 %, runner-up 53 %; threats 7, 7 and 6 of 10 over 122 late futures; the comparison of 6 candidates on 200 worlds ≈ 0.3 s; the showcase log (plan, 2 check-ins, 2 recommendations) 0.84 s |
| automatic action (test project, autonomy 3) | the overview after it 61.5 % = the action's shown chance 61.5 % (mean finish equal) |
| image recipe without Docker | environment 270 MB; healthy after 3.7 s; project created and planned through the API |
| screenshots `docs/ui/` | Polish 11 files, 1,317 kB; English 11 files, 1,184 kB (limit 3 MB per language) |
| e2e libraries | 3 packages, 1.96 MB downloaded, 7.1 MB extracted |
| `dist/sentinel-1.1.0.zip` | 19.9 MB, 623 files of commit c485ec9 (1.0.0: 16.9 MB, 476 files), built in 1.6 s, byte-identical on a second build |

Task-timing baseline (`tests/test_ui_usability.py`, Polish pages, `docs/usability/baseline-timing.json`;
machine time: no reading or thinking, the server's work included):

| # | Task | Clicks | Fields | Seconds |
| --- | --- | ---: | ---: | ---: |
| 1 | Create a project from the CSV template (wizard, pasted team, import, plan) | 9 | 4 | 2.2 |
| 2 | Tell when the project will most likely finish | 0 | 0 | 0.0 |
| 3 | Report an absence (a check-in with progress and the absence) | 6 | 5 | 0.4 |
| 4 | Decide on the recommendation (wait for it, open, approve) | 2 | 0 | 1.6 |
| 5 | Run the simulator to the end and compare | 3 | 0 | 29.8 |

## Commands for the owner
```bash
# Docker (not installed on this server): build, size, start time, a project through the API
docker build -t sentinel:1.1.0 .                       # time it; a few minutes the first time
docker image ls sentinel:1.1.0                         # SIZE, about 400 MB expected
docker run -d --name sentinel-smoke -p 127.0.0.1:8000:8000 sentinel:1.1.0
time sh -c 'until curl -fs http://127.0.0.1:8000/api/health; do sleep 0.5; done'
# then create a project as in docs/deploy.md ("Docker in WP9c"); docker rm -f sentinel-smoke
docker compose up -d --build && docker compose ps      # (healthy) after about 30 s

# The public demo (not started in the WP)
scripts/run_demo.sh start          # tmux session sentinel-demo, 127.0.0.1:8000
scripts/run_demo.sh check          # expects "OK: the limits count the visitor's address"
scripts/run_demo.sh funnel         # public: https://<machine>.<tailnet>.ts.net/
#   from a phone on mobile data: https://<machine>.<tailnet>.ts.net/api/client-address
scripts/run_demo.sh unfunnel       # tailscale funnel reset: nothing public
scripts/run_demo.sh stop
#   "Access denied" from tailscale funnel: once, sudo tailscale set --operator=$USER
#   (without sudo on WSL2: wsl -u root from Windows, then tailscale set --operator=kamil)

# The usability test: docs/usability/protocol-pl.md, results into a copy of results-template.md
uv run sentinel ui --data-dir ~/sentinel-test/P1     # a clean app per participant

# The release (built, not tagged)
uv run sentinel release --version 1.1.0   # again from the final commit; prints the tag command:
# git tag -a v1.1.0 -m "Sentinel 1.1.0" <commit> && git push origin v1.1.0
```

## Open issues / next steps
- Spec questions 1–4.
- Build the Docker image on a machine with Docker and record its size and start time.
- Run the usability test with 3–5 people and fill in the results template.
- The simulator's detailed report in Polish with Polish task names.
- Team changes after tracking starts and check-in corrections (WP9a) are still not in the UI.
