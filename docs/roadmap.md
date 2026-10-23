# Roadmap

| WP | Scope | Target | Status |
| --- | --- | --- | --- |
| WP−1 | Server infrastructure (WSL2, Tailscale, SSH, tmux, uv, Claude Code, Ollama) | 2026-10-20 | done |
| WP0 | Project scaffold, domain model (§1), PSPLIB fetch + loader, CPM bounds, tests | 2026-10-22 | done |
| WP1 | Serial SGS + priority rules, CP-SAT, RQ2 benchmark on J30/J60 | 2026-10-26 | done |
| WP2 | Simulator: stochastic durations, disruptions, daily semantics, NoReaction (§2–§3) | 2026-11-02 | done |
| WP3 | Monte Carlo forecasts and calibration (RQ3) | 2026-11-06 | done |
| WP4 | Baseline reactive policies (§7) | 2026-11-10 | done |
| WP5 | Goal & Needs Engine, candidates, rollout selector, permission gate (§4–§6) | 2026-11-16 | done (studies `results/wp5/20261022-102609-e9d131b3` main, `20261022-193948-592f7183` ablation, `20261022-234437-49965457` autonomy levels) |
| WP6 | LLM layer: client, cache, schemas; WBS extraction (RQ1), event parser, candidates, explanations | 2026-11-21 | todo |
| WP7 | Full experiments, statistics, figures (RQ4, RQ5) | 2026-11-25 | todo |
| WP8 | Minimal dashboard, reproduce command, release package | 2026-12-02 | todo |

Milestones: concept presentation ~2026-10-28 (needs WP1 table); submission 2026-12-02.

## Research questions

- **RQ1 (A):** Does validation with a repair loop improve LLM-generated WBS correctness?
- **RQ2 (A):** Does CP-SAT produce better schedules than priority-rule heuristics?
- **RQ3 (A):** How well calibrated are probabilistic completion forecasts?
- **RQ4 (B):** Does Sentinel reduce deadline overruns vs reactive policies without destabilising plans?
- **RQ5 (B):** What does the LLM contribute to the agent's decisions?
