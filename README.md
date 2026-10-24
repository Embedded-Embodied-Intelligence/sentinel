# Sentinel — AI-driven project management

Research prototype of a goal-driven agent that monitors a project under uncertainty,
detects threats to explicit goals (deadline, budget, plan stability) and selects
interventions by simulating their outcomes before acting. Scheduling relies on serial SGS
heuristics and Google OR-Tools CP-SAT; evaluation uses PSPLIB instances extended with
disruptions typical of software projects.

> Status: work in progress (course project at Rzeszów University of Technology, 2026).

## Repository map

- `docs/spec/model.md` — formal model (source of truth)
- `docs/spec/architecture.md` — architecture and package layout
- `docs/adr/` — architecture decision records
- `docs/roadmap.md` — work packages and status
- `docs/reports/` — work package reports
- `src/sentinel/` — Python package; `tests/` — pytest suite; `scripts/` — utilities

## Quick start

Requires [uv](https://docs.astral.sh/uv/); it installs Python 3.12 if missing.

```bash
uv sync                                               # environment from uv.lock
uv run pre-commit install                             # git hooks (ruff, detect-secrets, hygiene)
uv run python scripts/fetch_psplib.py --sets j30 j60  # PSPLIB into data/psplib (not committed)
uv run pytest -q                                      # tests; data tests skip without data/
uv run pytest -q -m "data or slow"                    # data tests and slow tests (> 30 s; data > 3 s)
uv run sentinel inspect j30/j301_1                    # instance summary, LB0, reference makespans
```

Quality gate before every commit:
`uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`.

Benchmark data come from PSPLIB (Kolisch & Sprecher 1997) and are downloaded, never
redistributed; `data/psplib/MANIFEST.json` records source URLs and SHA-256 checksums.

## Reproducing the results

Every number, table and figure of the article (English) and the course report (Polish) comes
from code: `configs/paper.toml` lists the 14 committed result runs in `results/` with the
SHA-256 of their manifests and raw outputs, and `sentinel paper` turns their summaries into
`paper/generated/` (LaTeX macros `numbers.tex`, tables `tab_rq1.tex` … `tab_rq5.tex`,
figures `fig_rq*.pdf`; Polish versions in `paper/generated/pl/`). It refuses a run that is
missing, a smoke run, recorded with uncommitted changes, or whose files differ from the
pinned hashes.

```bash
uv sync
uv run python scripts/fetch_psplib.py --sets j30 j60  # the RQ1 texts are narrated from PSPLIB
uv run sentinel reproduce --check                     # about 40 s, nothing recomputed
uv run sentinel paper                                 # writes paper/generated/ again
```

`reproduce --check` regenerates every summary of the 14 runs from their committed data files
and `paper/generated/` in a temporary directory, and compares every file byte for byte with
the committed one (117 files); exit status 0 means identical. It calls no LLM: the RQ1 error
analysis replays its sessions from the run's committed bundle.

**Full recomputation.** `uv run sentinel reproduce --commands` prints the prerequisites
(PSPLIB data, the `cpsat_det` baseline plans, the RQ5 decision states) and, per run, the
command recorded in its manifest with its recorded duration: about 23 h in total on the
4-core machine of `docs/infra/environment.md`, the longest 9.2 h (RQ4 main study), so run
them in `tmux`. A recomputed run gets a new directory under `results/`; configs that join
earlier runs read the committed ones.

**LLM runs without keys.** Each LLM run (RQ1, RQ5) commits its replay bundle
`llm_cache.jsonl.gz`; `--cache-file` answers every backend from it, without API keys,
Ollama or network, for example:

```bash
uv run python -m sentinel.experiments.wbs_study --config configs/wp6_rq1.toml \
  --out results/wp6 --cache-file results/wp6/20261023-215350-f5aad526/llm_cache.jsonl.gz
```

`--commands` prints this replay for each LLM run. The cloud answers came from
`openai/gpt-oss-120b` served by Groq through OpenRouter (provider pinned); a live rerun
would not return the same text, which is why the bundles are the reference.

## AI-assisted development

Code in this repository is written with the help of an AI coding assistant (Claude Code)
working from specifications and prompts authored and reviewed by the author. Design
decisions, the formal model and the evaluation protocol are the author's responsibility and
are documented in `docs/`.

## License

MIT — see `LICENSE`.
