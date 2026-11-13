# Sentinel — architecture

## Layers

| Layer | Responsibility | Deterministic? |
| --- | --- | --- |
| Interpretation (LLM) | parse events, propose candidates in JSON grammar, explain decisions (spec §10); edit a person's text for an audience (§11.9, ADR-0038) | via record/replay cache |
| Decision | state model, Goal & Needs Engine, candidate selection, permission gate | yes |
| Computation | validation, SGS heuristics, CP-SAT, Monte Carlo rollouts, simulator | yes (seeded) |

The LLM proposes and interprets; the solver checks constraints; the goal engine chooses. LLM
output enters the decision layer only as validated, compiled objects (spec §10).

## Package layout (src layout)

```
src/sentinel/
  __init__.py
  cli.py                 # argparse entry point: `uv run sentinel ...`
  release.py             # WP8: `sentinel release`, the zip of `git archive` HEAD (no tag)
  model/                 # §1 domain: instance.py, schedule.py (Schedule, validate_schedule)
  data/                  # PSPLIB loading/conversion, reference solutions (paths, parsing)
  scheduling/            # bounds.py (CPM, LB0), sgs.py, priority_rules.py, cpsat.py
  simulation/            # WP2: stochastic durations, events, daily execution semantics
  forecasting/           # WP3: Monte Carlo makespan distributions, calibration
  policies/              # WP4: NoReaction, AlwaysSubstitute, FullResolve, StableResolve
  agent/                 # WP5: needs, candidates, rollout selector, permission gate
  llm/                   # WP6: clients (Ollama; Groq and OpenRouter through one OpenAI-compatible
                         #   client), record/replay cache, schemas, prompts (English); WP14:
                         #   whisper.py (Groq's Whisper for recordings, nothing stored, ADR-0031)
  wbs/                   # WP6a: narrator, extraction, validation, scores (RQ1)
  interpret/             # WP6b: event parser, action grammar and compiler, explanations (§10);
                         #   WP20: redaction.py (role 4), tracked.py (the word-level diff of
                         #   tracked changes), facts.py (the fact guard), spec 11.9
  experiments/           # runners, config loading, manifests, summaries, tables/figures; WP7:
                         #   paper.py (`sentinel paper`), reproduce.py (`sentinel reproduce`);
                         #   WP20: report_corpus.py, rq6_study.py (RQ6), paper_rq6.py
  dashboard/             # WP8: project cockpit (`sentinel dashboard`), one self-contained HTML
  evidence/              # WP18: the evidence registry of v3 (model.py, load.py), the quote check
                         #   (verify.py: the documented normalisation) and page text (text.py);
                         #   data/ (registry.json, decisions.json, boundary-map.json) ships with
                         #   the package (WP19, ADR-0037); docs/research/ describes them; WP20:
                         #   survey.py (the survey's aggregate, data/survey.json once imported)
  app/                   # WP9: the application (spec section 11): live projects (live.py),
                         #   planning.py (plan, forecast, recommendation and its comparison),
                         #   simulator.py, events.py and store.py (SQLite event log), services.py,
                         #   views.py, api.py (FastAPI, `sentinel ui`), security.py (demo
                         #   sessions, CSRF, client addresses), showcase.py, names.py and
                         #   vocabulary/<lang>.toml (names of the example projects per language)
    llm.py               # the application's LLM service: settings, keys (mode 0600), the daily
                         #   cap, explanations and recordings (WP11, WP14)
    message_reader.py    # WP14: the reader of a check-in message: items of the form, unparsed
                         #   parts and questions (spec 11.3, ADR-0032)
    date_words.py        # WP14: dates named by the model in words, settled by code on the
                         #   project calendar (ADR-0032)
    calendar.py          # WP12: working days with Polish holidays and company days off (11.1)
    decisions.py         # WP15: validity date, cost of delay, corrections, brief (spec 11.8)
    feed.py              # WP16: the iCalendar text of a project's calendar feed (ADR-0035)
    attack.py            # WP19: "Próba ataku" of Uprawnienia AI through the message flow, with
                         #   the recorded answer attack_replay.json (scripts/record_attack.py)
    reports.py           # WP20: Raporty's drafts (memory only until saved), versions, export
    finance.py           # WP20: Finanse's portfolio lines and budget requests (spec 11.9)
    ui/                  # WP9b: the pages: Jinja2 templates, text.py (catalogue PL/EN), forms,
                         #   charts (SVG), routes per screen; static/ (CSS, vendored HTMX)
      v2/                # the v2 interface under /v2 (ADR-0033; docs/design/v2-spec.md):
                         #   WP15: shell (frame, theme, live banner), numbers (states, "na 100",
                         #   time reserve), status, overview (Pulpit), decision (Decyzja and
                         #   Decyzje), report (Raport, its per-task form and the cards; WP16),
                         #   voice, start (Start, Projekty), wizard (Nowy projekt);
                         #   WP16: log (Dziennik, CSV), plan (Harmonogram, Zadania, Zespół),
                         #   lab (Co jeśli?, Symulator), settings (Ustawienia, project settings),
                         #   calendar (secret link and feed, ADR-0035);
                         #   WP19 (docs/design/v3-spec.md): evidence (the "Dowód" point and
                         #   panel, Źródła, Mapa granic), rules (Uprawnienia AI, Ludzie),
                         #   text_v3.py; the decision page's "Twoja ocena" (spec 11.8);
                         #   WP20: reports (Raporty), finance (Finanse), text_v3_work.py,
                         #   Mapa granic's survey view;
                         #   text.py (its catalogue); templates/v2/, sentinel-v2.css/js
scripts/                 # one-off utilities, e.g. fetch_psplib.py, fetch_evidence.py (WP18: the
                         #   registry's open sources, their text and the quote check); record_attack.py
                         #   (WP19); ui_v3_screenshots.py (WP19, WP20); make_rq6_corpus.py and
                         #   import_survey.py (WP20); run_demo.sh (public demo),
                         #   setup_e2e_libs.sh (Chromium libraries without root)
configs/                 # experiment configs (TOML), one per experiment; paper.toml (WP7)
tests/                   # pytest; fixtures in tests/fixtures/
data/                    # downloaded benchmark data (gitignored)
results/<wp>/<run_id>/   # experiment outputs (small files committed)
paper/generated/         # WP7: macros, tables, figures of the papers (English; Polish in pl/)
docs/                    # spec, ADRs, notes, reports, prompts
```

Modules for later WPs are created when their WP starts, not before. Only `wbs/`, `interpret/`,
`experiments/`, `dashboard/` and `cli.py` import `llm/`; no simulation, scheduling, forecasting,
policy or agent module imports `llm/`, `wbs/`, `interpret/` or `dashboard/` (a test enforces
it), so no rollout can call an LLM. The cockpit calls an LLM only after its runs, to explain
recorded decisions, and only through the cache (ADR-0021). The application (`app/`) may import
every other package; no research package imports `app/`, and only `app/` and `cli.py` import the
web stack (FastAPI, uvicorn, Jinja2; a test enforces both, ADR-0022).

## Interfaces (stable contracts)

- `ProjectInstance` (pydantic, frozen): activities, roles, workers; derived helpers
  (`predecessors`, `topological_order`, `n_real`). Constructed via validated
  factory functions only.
- `Schedule`: mapping activity id → start time; `makespan(instance)`.
- `validate_schedule(instance, schedule) -> list[Violation]`: empty list means feasible (§1.3).
- Scheduling functions are pure: `(instance, params, rng?) -> Schedule | SolveResult`.
- Every randomized function takes an explicit `numpy.random.Generator`.
- LLM calls: `LlmClient.complete(messages, schema=..., seed=..., ...) -> LlmResponse` through the
  record/replay cache (ADR-0018), over `OllamaClient` or the `OpenAICompatibleClient` of Groq
  (`GroqClient`) and OpenRouter (`OpenRouterClient`, provider pinned); a call may pass a domain
  validator, which a cache without prompts runs before it stores the answer (spec §10).
  `interpret.actions.compile_proposal(...) -> Candidate | Issue` is the only way a proposal
  becomes a candidate (spec §10.3).

## Data paths

- `data/psplib/<set>/<instance>.sm` — e.g. `data/psplib/j30/j301_1.sm`
- `data/psplib/solutions/<set>_<type>.sm` — `type ∈ {opt, hrs, lb}`
- `data/psplib/MANIFEST.json` — source URLs, download time, SHA-256 per archive
- `data/derived/` — reproducible derived data (gitignored): baseline plans, recorded decision
  states (`decision_states/`, WP6b)
- `data/evidence/` — the open sources of the evidence registry (WP18, ADR-0036; gitignored, never
  committed): `raw/<file>` as downloaded (or put there by the owner for a paywalled article),
  `text/<file>.txt` their plain text, `MANIFEST.json` (URL, time, size, SHA-256)
- `data/llm_cache/` — record/replay caches of LLM calls, one JSON-lines file per backend and
  study (gitignored); a run commits its replay bundle
- the application's data directory (`sentinel ui --data-dir`, default
  `$XDG_DATA_HOME/sentinel`, outside the repository; `/data`, a named volume, in Docker):
  `sentinel.db` (SQLite: projects, the event log, sessions, jobs, the demo's request log, and
  each project's calendar row: report reminder and the nonce of its link, ADR-0035),
  `settings.json` (the LLM provider and its keys, mode 0600, never returned by the API),
  the saved reports and budget requests in `sentinel.db` (WP20, per session),
  `secret.key` (the key that signs cookies and derives calendar links) and `llm_cache/` (caches
  without prompts, spec section 10)

## Application (WP9)

`sentinel ui` serves the FastAPI app of `app/api.py` (uvicorn, 127.0.0.1 by default). The API
and the pages (`app/ui/`, ADR-0025) call the services of `app/services.py`, which hold no HTTP:
live projects (`app/live.py`, spec section 11) and simulator projects (`app/simulator.py`) are
rebuilt from their event log in the store (`app/store.py`, ADR-0023); long operations (plan,
forecast, recommendation, simulator advance, cockpit) run in a background worker
(`app/jobs.py`) with a job id and progress. With `--demo` every visitor gets an anonymous
sandbox (signed cookie, limits, 24 h expiry, CSRF tokens; ADR-0024).

Two interfaces share these services (ADR-0033): the first at `/` (WP9b–WP14) and v2 at `/v2`
(WP15–WP16: Start, Projekty, Pulpit, Raport, Decyzje and Decyzja, Dziennik, Plan, Laboratorium,
Ustawienia and the project settings with its calendar, Nowy projekt). A calendar fetches a
project's feed at `/calendar/{project}/{token}.ics` without a session; the link's token, derived
from the server key, is its only key (ADR-0035).

### Deployment options (WP9c, ADR-0026)

| Option | Who | How | Notes |
| --- | --- | --- | --- |
| Laptop | one manager | `uv sync`, `uv run sentinel ui` → http://127.0.0.1:8000 | data in `~/.local/share/sentinel` |
| Company server | a team, IT runs it | `docker compose up -d` (multi-stage image, Python 3.12 slim, non-root, `HEALTHCHECK` on `/api/health`), optional `ollama` profile for a local AI | data in the `sentinel-data` volume; put it behind the company's HTTPS proxy |
| Public course demo | anyone with the link | `scripts/run_demo.sh` (`sentinel ui --demo` on 127.0.0.1 under tmux or a user systemd service) and `tailscale funnel` (HTTPS) | per-visitor sandboxes; `X-Forwarded-For` trusted only from 127.0.0.1; `docs/deploy.md` |

## Results

`results/<wp>/<run_id>/` with `run_id = <UTC yyyymmdd-HHMMSS>-<config hash[:8]>`, containing
`manifest.json`, `results.csv` and generated summaries (`summary.md`, LaTeX tables, figures).
See the `experiment-run` skill.

## Paper artifacts and reproduction (WP7)

- `configs/paper.toml` lists the committed runs the papers cite, with the SHA-256 of their
  manifests and raw outputs. `sentinel paper` turns their summaries into `paper/generated/`:
  `numbers.tex` (LaTeX macros, each with its source cell), `tab_rq1.tex` … `tab_rq5.tex`,
  `fig_*.pdf`, the Polish versions in `pl/`, `numbers.md` and `MANIFEST.json` (ADR-0020).
- RQ6 (WP20) has its own pinned config, `configs/paper_rq6.toml` (written by `sentinel paper
  --pin-rq6 <run>` once the full run exists), and its own artifacts in `paper/generated/rq6/`, so
  that the earlier artifacts stay byte for byte as they are; `sentinel paper` and `reproduce`
  handle both.
- `sentinel reproduce --check` regenerates every committed summary and `paper/generated/` in a
  temporary directory, without recomputation or LLM calls, and compares them byte for byte;
  `sentinel reproduce --commands` prints the commands that recompute each run.
