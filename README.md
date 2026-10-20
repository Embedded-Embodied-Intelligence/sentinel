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

## Quick start

Setup instructions are added in WP0.

## AI-assisted development

Code in this repository is written with the help of an AI coding assistant (Claude Code)
working from specifications and prompts authored and reviewed by the author. Design
decisions, the formal model and the evaluation protocol are the author's responsibility and
are documented in `docs/`.

## License

MIT — see `LICENSE`.
