# Sentinel — architecture

## Layers

| Layer | Responsibility | Deterministic? |
| --- | --- | --- |
| Interpretation (LLM) | parse events, propose candidates in JSON grammar, explain decisions (spec §10) | via record/replay cache |
| Decision | state model, Goal & Needs Engine, candidate selection, permission gate | yes |
| Computation | validation, SGS heuristics, CP-SAT, Monte Carlo rollouts, simulator | yes (seeded) |

The LLM proposes and interprets; the solver checks constraints; the goal engine chooses. LLM
output enters the decision layer only as validated, compiled objects (spec §10).

## Package layout (src layout)

```
src/sentinel/
  __init__.py
  cli.py                 # argparse entry point: `uv run sentinel ...`
  model/                 # §1 domain: instance.py, schedule.py (Schedule, validate_schedule)
  data/                  # PSPLIB loading/conversion, reference solutions (paths, parsing)
  scheduling/            # bounds.py (CPM, LB0), sgs.py, priority_rules.py, cpsat.py
  simulation/            # WP2: stochastic durations, events, daily execution semantics
  forecasting/           # WP3: Monte Carlo makespan distributions, calibration
  policies/              # WP4: NoReaction, AlwaysSubstitute, FullResolve, StableResolve
  agent/                 # WP5: needs, candidates, rollout selector, permission gate
  llm/                   # WP6: client (Ollama/Groq), cache, schemas, prompts (English)
  wbs/                   # WP6a: narrator, extraction, validation, scores (RQ1)
  interpret/             # WP6b: event parser, action grammar and compiler, explanations (§10)
  experiments/           # runners, config loading, manifests, summaries, tables/figures
scripts/                 # one-off utilities, e.g. fetch_psplib.py
configs/                 # experiment configs (TOML), one per experiment
tests/                   # pytest; fixtures in tests/fixtures/
data/                    # downloaded benchmark data (gitignored)
results/<wp>/<run_id>/   # experiment outputs (small files committed)
docs/                    # spec, ADRs, notes, reports, prompts
```

Modules for later WPs are created when their WP starts, not before. Only `wbs/`, `interpret/`
and `experiments/` import `llm/`; no simulation, scheduling, forecasting, policy or agent module
imports `llm/`, `wbs/` or `interpret/` (a test enforces it), so no rollout can call an LLM.

## Interfaces (stable contracts)

- `ProjectInstance` (pydantic, frozen): activities, roles, workers; derived helpers
  (`predecessors`, `topological_order`, `n_real`). Constructed via validated
  factory functions only.
- `Schedule`: mapping activity id → start time; `makespan(instance)`.
- `validate_schedule(instance, schedule) -> list[Violation]`: empty list means feasible (§1.3).
- Scheduling functions are pure: `(instance, params, rng?) -> Schedule | SolveResult`.
- Every randomized function takes an explicit `numpy.random.Generator`.
- LLM calls: `LlmClient.complete(messages, schema=..., seed=..., ...) -> LlmResponse` through the
  record/replay cache (ADR-0018); `interpret.actions.compile_proposal(...) -> Candidate | Issue`
  is the only way a proposal becomes a candidate (spec §10.3).

## Data paths

- `data/psplib/<set>/<instance>.sm` — e.g. `data/psplib/j30/j301_1.sm`
- `data/psplib/solutions/<set>_<type>.sm` — `type ∈ {opt, hrs, lb}`
- `data/psplib/MANIFEST.json` — source URLs, download time, SHA-256 per archive
- `data/derived/` — reproducible derived data (gitignored): baseline plans, recorded decision
  states (`decision_states/`, WP6b)
- `data/llm_cache/` — record/replay caches of LLM calls, one JSON-lines file per backend and
  study (gitignored); a run commits its replay bundle

## Results

`results/<wp>/<run_id>/` with `run_id = <UTC yyyymmdd-HHMMSS>-<config hash[:8]>`, containing
`manifest.json`, `results.csv` and generated summaries (`summary.md`, LaTeX tables, figures).
See the `experiment-run` skill.
