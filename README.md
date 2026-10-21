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
uv run pytest -q -m "data or slow"                    # data tests and slow (> 30 s) tests
uv run sentinel inspect j30/j301_1                    # instance summary, LB0, reference makespans
```

Quality gate before every commit:
`uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`.

Benchmark data come from PSPLIB (Kolisch & Sprecher 1997) and are downloaded, never
redistributed; `data/psplib/MANIFEST.json` records source URLs and SHA-256 checksums.

## AI-assisted development

Code in this repository is written with the help of an AI coding assistant (Claude Code)
working from specifications and prompts authored and reviewed by the author. Design
decisions, the formal model and the evaluation protocol are the author's responsibility and
are documented in `docs/`.

## License

MIT — see `LICENSE`.
