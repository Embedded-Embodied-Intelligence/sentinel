# WP8 report — project cockpit, release package, final housekeeping

- Date: 2026-10-24
- Commit(s): 8bd188f (`spec: cache privacy for real data; architecture (v1.9.2)`), 9ef9386
  (answer 2), 0ecedc2 (cockpit), c3e31a2 (example script), aa3c8c2 (row caption, singular forms),
  0bf86dc (example cockpits), 53edfd7 (release command, version 1.0.0), cc5cebe (README); the
  report commit follows them

## Summary
`sentinel dashboard` re-simulates one world of the studies under two policies on the same seed
and writes one self-contained HTML page (no server, no URL, no timestamp; 88–221 kB): key
figures side by side, the Gantt chart of baseline plan and realised execution with the day's
disruptions, the agent's own risk forecast at every deliberation, and the decision log with
triggers, needs, choice, runner-up, deciding component, gate outcome and an explanation (a
template from the record, faithful by the §10.4 check, or an LLM through the cache with its
badge); English or Polish labels. Three Polish example cockpits, chosen by a deterministic query
over the WP5 results and checked against their study rows, are in `docs/dashboard/`.
`sentinel release --version 1.0.0` builds `dist/sentinel-1.0.0.zip` from `git archive` of HEAD
with a generated `RELEASE.md`. Spec v1.9.2 states the WP7 answers; answer 2 is implemented
(domain issues withheld from caches without prompts); the README has an overview, a text
diagram and a results section generated from `paper/generated/numbers.tex`.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.9.2 commit; quality gate and `-m "data or slow"` pass; task-4 tests exist and pass | `git show --stat 8bd188f`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (8bd188f: `docs/spec/model.md` v1.9.2 §10, `docs/spec/architecture.md`; ruff clean, 277 files formatted, mypy: no issues in 104 source files; `pytest -q`: 425 passed, 11 deselected in 72.0 s; `-m "data or slow"`: 25 passed, 411 deselected in 493.6 s; task-4 tests: `tests/test_dashboard.py` (tiny cockpit: parses, every section, no URL, at most 2 MB, byte-identical for a fixed seed, Polish labels; templates use only record values; LLM badges; J30 smoke reproducing its WP5 row), `tests/test_release.py` (dirty tree, version, data, secrets, caches, contents, identical bytes)) |
| 2 | Three example cockpits committed, listed with one screenshot-free description each | `uv run python scripts/example_cockpits.py` (at aa3c8c2, committed 0bf86dc) | PASS (three pages with Polish labels in `docs/dashboard/` and a generated README with the rules and commands; each reproduces its WP5 row, which the script checks before writing; descriptions under Numbers; a rerun of one command gives the same SHA-256) |
| 3 | `dist/sentinel-1.0.0.zip` builds from a clean tree; file list summarised | `git status --short` (empty); `uv run sentinel release --version 1.0.0` (at cc5cebe) | PASS (16.9 MB, 476 files of commit cc5cebe, byte-identical on a second build; no `data/`, no `.env` other than `.env.example`, no cache other than the 9 committed replay bundles; summary under Numbers; tag command printed, not run) |
| 4 | README updated; report and roadmap; pushed; clean tree | `git push`; `git status --short` | PASS (README overview, text diagram, generated results section and links, cc5cebe; this report, `docs/notes/WP8.md`, ADR-0021, roadmap `WP8: done`; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.9.2: §10 stores an invalid answer, and with a domain validator a
  schema-valid answer with domain issues, only as its issue list for `store_prompts = false`.
  `docs/spec/architecture.md`: OpenAI-compatible client with Groq and OpenRouter, `paper.py` and
  `reproduce.py`, `paper/generated/`, the paper and reproduce commands; `dashboard/`,
  `release.py`, the import rule with the cockpit.
- `src/sentinel/llm/core.py`: `DomainIssue`, `DomainValidator`, error kind `domain`,
  `withhold_invalid(..., validator)`; `client.py`: `complete(..., validator=None)`; `cache.py`,
  `__init__.py`: docstrings and exports. ADR-0018 amendment.
- `src/sentinel/interpret/events.py`: issue event index, `domain_issues`, `withheld_issue`, the
  parser passes its validator; `src/sentinel/wbs/extract.py`: `domain_issues` (activity
  indices), `withheld_issue`, both calls pass the validator.
- `src/sentinel/dashboard/` (new): `world.py` (catalogue of policies, world, checked runs with
  the agent's observations, forecasts), `assemble.py` (KPIs, Gantt rows, day events, decision
  log), `explain.py` (record-only templates EN/PL, LLM explainer through the cache), `labels.py`
  (EN/PL words, palette), `svg.py` (Gantt and risk charts), `page.py` (HTML, CSS, script),
  `cockpit.py` (options, build, provenance, save).
- `src/sentinel/release.py` (new): release zip, checks, `RELEASE.md`.
- `src/sentinel/experiments/readme.py` (new): README section from `numbers.tex`.
- `src/sentinel/cli.py`: `dashboard`, `release`; `paper --readme` (the section is rewritten
  when `sentinel paper` writes the committed `paper/generated/`).
- `scripts/example_cockpits.py` (new); `docs/dashboard/` (three cockpits, README).
- `pyproject.toml`: version 1.0.0, ruff `allowed-confusables` (en dash, multiplication sign);
  `uv.lock`: version 1.0.0.
- Tests: `test_dashboard.py` (new, 6 + 1 data/slow), `test_release.py` (new, 9),
  `test_readme.py` (new, 2), `test_llm.py` (+1 domain issues; import rule with the cockpit),
  `test_interpret_events.py` (+1), `test_wbs_extract.py` (+1).
- Docs: README, ADR-0021, `docs/notes/WP8.md`, this report, roadmap.

## Decisions
- **Re-simulated study worlds** (ADR-0021). The committed rows hold counts only, so the cockpit
  runs the world again with the study's settings and the variant's parameters; the example
  script refuses a page whose makespan, on-time flag, hires, substitutions, deliberations,
  escalations or approvals differ from its row (none did).
- **The risk chart is the agent's forecast.** NOOP's rollouts of each deliberation are repeated
  on the agent's worlds with its rollout count; P(C ≤ D) must equal the record's (checked at
  every deliberation, else the build fails) and the same rollouts give the P10–P90 band. The
  agent and `DecisionRecord` are unchanged, so the RQ5 renderings, caches and decision states
  stay valid. A policy without forecasts gets the same estimate every T_r days.
- **Hand-built inline SVG** instead of matplotlib output: exact bytes, small pages, marks with
  `<title>` tooltips; shapes, fills and line styles plus direct labels and legends tell series
  apart without colour (WP7 palette and slots). The compared policy's Gantt chart is collapsed
  and opened before printing.
- **Template explanations in the role-3 schema**, numbers derived from the values as rendered,
  so the §10.4 check applies; Polish templates too (labels are Polish for the presentation; LLM
  texts stay English). LLM explanations only for deliberations that passed the needs gate (§10.4),
  cache `data/llm_cache/dashboard/<backend>.jsonl` with full records (synthetic worlds).
- **Deadline handling.** δ_D defaults to the Sentinel variant's; every Sentinel works towards
  D(δ_D); a baseline runs with the day limit of the studies' largest slack and is judged against
  D(δ_D) post hoc, as in the summaries.
- **Answer 2 scope.** The event parser and the WBS extraction pass their validators; stored
  issues keep kinds and indices (event index, activity index), never names. Proposals pass none
  (their schema is the grammar; their domain check is compilation on the state), nor do
  explanations (checked for faithfulness after the call).
- **Release checks.** Untracked files count as dirty; `--version` must equal `pyproject.toml`'s,
  so the project version is now 1.0.0; `.env.example` (variable names, a default Ollama host) is
  included and its secret-like variables must be empty; entries carry the commit time, so the zip
  is reproducible.
- **README section** from the English macros, written only when `sentinel paper` writes the
  configured `paper/generated/`; a test compares the committed README with the section.
- ADRs created: ADR-0021 (static project cockpit); ADR-0018 amended (domain issues).

## Deviations
- **More than the listed options**: `--root` and `--cache` (data root and baseline cache, used by
  the tests) and `sentinel paper --readme`.
- **More than the listed KPIs**: deliberations, and removed activities when DESCOPE ran; the
  compared policy's Gantt chart in a collapsed section.
- **`.env.example` is in the release**: the WP asks for no `.env*`; the file holds names only
  (and the default `OLLAMA_HOST`), so it is kept and checked instead of excluded.
- **Files beyond the WP's list**: `llm/core.py`, `client.py`, `cache.py`, `__init__.py`,
  `interpret/events.py`, `wbs/extract.py` (answer 2), `pyproject.toml` and `uv.lock` (version,
  ruff), `tests/test_llm.py` (the import rule now also keeps simulation, agent and policy
  modules away from `sentinel.dashboard`, and allows the cockpit and `cli.py`).

## Spec questions
1. **Domain validators of roles 2 and 3 for real data.** Spec v1.9.2 names the event parser and
   the WBS extraction. Should a proposal answer whose compilation fails (an unknown role name,
   an ineligible SUBST) and an explanation that fails the §10.4 check also be stored as issue
   lists when `store_prompts = false`? Reading used: no; compilation needs the state and CP-SAT,
   and the faithfulness check runs after the call.
2. **The risk band of a chosen action.** The record keeps the chosen candidate's p̂ and T̂ but no
   quantiles, so the cockpit's band is NOOP's ("if nothing is done") and the chosen action is a
   point. Should `DecisionRecord` keep makespan quantiles per candidate? That would change the
   record's rendered form for RQ5 (not done).

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2, CPython 3.12.15, uv 0.13.2; idle machine (load
0.1–0.3), no Ollama run, no LLM call in the whole WP.

**Tests.** Default `pytest -q`: 425 passed, 11 deselected in 72.0 s (405 in 70.8 s at the start
of WP8; the 20 new default tests take about 1.7 s: cockpit 1.3 s, release 0.4 s). `-m "data or
slow"`: 25 passed in 493.6 s (24 in 480.1 s at the end of WP7; the J30 cockpit test takes
9.7 s).

**Cockpits.** A tiny cockpit builds in 0.5 s, the J30 smoke cockpit (j301_1, r0, λ_A = 0.01,
32 deliberations) in 9.7 s, the three examples in 82 s; every deliberation's forecast equals the
agent's p̂.

| Cockpit (`docs/dashboard/`) | World | Size | What it shows |
| --- | --- | ---: | --- |
| `j30_sentinel_on_time.html` | j30/j3026_7, r1, D = 68 | 155 kB | Sentinel finishes after 68 days (on time), NoReaction after 86 (18 days late); 47 deliberations, 4 plan changes moving 51 planned starts, 9 temporary workers (overtime cost 138.0), 1 substitution |
| `j30_escalation.html` | j30/j301_9, r2, D = 59, Λ = 2 | 88 kB | Sentinel Λ=2 on time after 57 days, NoReaction 1 day late; 18 deliberations, a RESEQ-S applied at once, an overtime action deferred on day 35, SUBST(22) escalated on day 50 and approved on day 51 |
| `j60_overtime.html` | j60/j6010_7, r1, D = 83 | 221 kB | Sentinel on time after 82 days, NoReaction 4 days late; P(on time) without action is 0 on day 10, and 59 deliberations with 6 plan changes (173 planned starts moved), 19 temporary workers (overtime cost 349.5) and 1 substitution bring it back |

Rules (λ_A = 0.01): the largest NoReaction − Sentinel gap among J30 worlds where only Sentinel
meets D(0.2) (main run); the fewest deliberations among on-time J30 worlds of Sentinel Λ = 2 with
an escalation and an applied approval (ablation run); the largest overtime cost among on-time
J60 worlds of Sentinel with temporary workers (main run); ties by instance, then replication.

**Release** (`dist/sentinel-1.0.0.zip`, commit cc5cebe, 1.6 s, 16.9 MB, 23.1 MB unpacked, SHA-256
`c15a6cc0…ba171`, identical on a second build): 476 files under `sentinel-1.0.0/`:

| Path | Files | Path | Files |
| --- | ---: | --- | ---: |
| `src/sentinel` | 110 | `docs/adr` | 22 |
| `tests` | 59 | `docs/notes`, `docs/prompts`, `docs/reports` | 18 each |
| `results` (wp1 6, wp2 6, wp3 36, wp4 18, wp5 30, wp6 57) | 153 | `docs/dashboard` | 4 |
| `paper/generated` | 26 | `docs/spec`, other `docs` | 2, 4 |
| `configs` | 16 | `.claude` (project skills) | 5 |
| `scripts` | 10 | root files (`README.md`, `CLAUDE.md`, `pyproject.toml`, `uv.lock`, `LICENSE`, `.env.example`, …) and `RELEASE.md` | 10 + 1 |

At the report commit the archive also holds `docs/reports/WP8.md` and `docs/notes/WP8.md`.

## Commands for the owner
- Rebuild the release at the final commit (2 s): `uv run sentinel release --version 1.0.0`;
  with the final PDFs: `uv run sentinel release --version 1.0.0 --include <article.pdf>
  --include <report.pdf>` (after committing everything; the zip is not committed).
- Tag when ready (not done): the command printed by `sentinel release`, e.g.
  `git tag -a v1.0.0 -m "Sentinel 1.0.0" <commit> && git push origin v1.0.0`.
- Optional LLM explanations in a cockpit (needs Ollama, or `OPENROUTER_API_KEY` in `.env`):
  `uv run sentinel dashboard --set j30 --instance j3026_7 --replication 1 --lang pl --explain
  ollama --out cockpit_llm.html` (47 calls, one per deliberation, through
  `data/llm_cache/dashboard/`).

## Open issues / next steps
- The article and the course report (`docs/deliverables/` through `--include`).
- Spec questions 1–2.
- Default `pytest -q` is at 72 s of its 75 s budget.
