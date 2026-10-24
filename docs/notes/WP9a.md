# WP9a notes — application back end: live projects, simulator, services and HTTP API

**Purpose.** The engine becomes an application for a project manager (spec v2.0 §11): a *live
project* updated at check-ins, whose recommendations are Sentinel deliberations, and a
*simulator project* on a PSPLIB world. The research semantics (§1–§10) are untouched: the app
maps what the manager enters onto `ProjectInstance`, plan and `Observation`, and maps Sentinel's
decisions back through the engine's own `rehearse`.

**Live mapping** (`app/live.py`, spec §11.1–§11.3).

| Manager enters | Model |
| --- | --- |
| start date `d₀`, dates | day `t` = working days since the first working day ≥ `d₀`; a start date `s` → `S_j = first(s)`, a finish date `f` → `F_j = last(f) + 1`, a deadline `d_D` → `D = last(d_D) + 1`, a makespan `C` shown as `date(C − 1)` |
| check-in dated `d` | observation of step 3 of day `t = last(d) + 1` (the state at the end of `d`) |
| people with roles (free text) | roles in order of their first person (matched without case, spacing, final plural *s*), `R_k` = people, workers in the order listed (dispatch prefers them) |
| task: duration, crew per role, predecessors, optional | activity `1..n` in list order, source/sink edges added; optional tasks = `O` (no successors allowed) |
| presets | PERT `confident` (0.9, 1, 1.3), `typical` (0.8, 1, 1.6), `uncertain` (0.7, 1, 2.0); `λ_A` calm 0.005, typical 0.01, turbulent 0.02; `λ_S` 0.01, `λ_N` 0.02, `E[L]` 3 |
| in progress, x % | `e_j = x · p_j · ΠF` rounded half up to whole crew-member days (`e_j M_j` integer, as `state_from_observation` requires) |
| done, finish date | status done, `F_j`; `e_j = p_j · ΠF` |
| no start date | `S_j` = planned start clamped to [previous check-in day, last possible day] and ≥ predecessors' `F_i` |
| no crew named | §3.1 (b): lowest-id idle present workers per role at `S_j`, new starts in order (start, plan, id); else the named crew (no one reserved elsewhere that day) |
| absence (first day, return date) | `present = false`, `absent_since = first(a)`, `announced = first(r) − first(a)` (1 without a return date, open until a later check-in closes it) |
| +N days / ×F | `F = (R + N)/R`, `R` the §5.2 deterministic remaining work after the check-in's progress; shock `(j, e_j, F)` appended |
| new task (after, before) | D3-style insertion `i → new → s`, ids `n + 2, …`, planned start of §3.1 (e) |
| cost so far | `Σ e_j · (daily cost of the crew's people)` + temporary workers' pay `1.5 c_k` per hired day |

Approving an action runs `approve` (§4: operations re-validated, plan part re-planned) and
`rehearse` on the current observation; the observation it leaves is mapped back: planned starts,
crews (substitutes take the replaced members' slots), temporary workers ("Temporary <role> n",
window `[t, t + H)`, leaving rules of §4), SUBST handovers `(j, e_j, m_j o_j)` and removed tasks.
Every check-in and action is stored with its resolved effects, so replaying the log needs no
solver and no rollout (ADR-0023). A check-in, the rebuilt observation and the engine agree: every
resolved state passes `state_from_observation` and `planning_view` (`LiveProject.check`).

**Recommendation** (`app/planning.py`, §11.5). `Sentinel(params, seed).deliberate(observation)`
with spec §8 parameters, `Λ` of the project and DESCOPE if optional tasks remain; the epoch seed
is `derive_seed(seed, "sentinel", t)`. The impacts of NOOP, the choice and the runner-up re-run
their rollouts on the same worlds (`Evaluator.extend`, checked against the record's `p̂`) for
the mean makespan, shown as the expected finish date. `ℓ < Λ` without DESCOPE applies at once;
otherwise the manager approves, rejects or postpones; there is no deferral. Explanations: the
WP8 template (faithful by construction, EN/PL) and optionally an LLM one with the §10.4 badge.

**Forecast** (§11.4). 200 NoReaction rollouts with `derive_seed(seed, "forecast", t)` (the
forecaster's own layout, identical makespans); risk drivers = tasks on the critical chain (tight
precedence links `F_i = S_j`, else tight links with a common role) in the most rollouts.

**Simulator** (`app/simulator.py`, §11.6). The world of replication `r` of the studies
(`derive_seed(2026, set, stem, r)`), the cached `cpsat_det` plan, `D` from `C*` (opt/hrs), IT
role names, narrator task names and a roster seeded per instance. The engine state and `Run` are
built as in `simulate` and executed with `open_day`/`close_day`, so a run advanced in any steps
equals `simulate` (tested on the tiny fixture and on j301_1 with Sentinel).

**API** (`app/api.py`, prefix `/api`; jobs answer 202 and are polled at `/api/jobs/{id}`).

| Endpoint | Purpose |
| --- | --- |
| `GET health`, `GET session` | status and version; demo flag, CSRF token, limits, LLM availability |
| `GET/PUT settings/llm` | provider, model, Ollama host, whether a key is set (never the key); not in the demo |
| `GET/POST projects`, `POST projects/validate` | list; create a live project; issues of a definition |
| `GET/DELETE projects/{id}`, `PUT projects/{id}/definition`, `GET projects/{id}/events` | view (live or simulator), delete, edit, the event log |
| `POST projects/{id}/plan`, `…/forecast`, `…/recommendations` | jobs: baseline plan, forecast, deliberation |
| `POST projects/{id}/checkins` | apply a check-in; starts the recommendation job |
| `POST projects/{id}/recommendations/{seq}/decision`, `…/explanation` | approve, reject or later; LLM explanation (job) |
| `GET projects/{id}/export.json`, `…/plan.csv`; `POST …/cockpit` | exports; the cockpit page (job, then `GET jobs/{id}/cockpit.html`) |
| `POST import/csv`, `POST import/json`, `GET templates/{tasks,team}.csv` | imports with per-row messages; templates |
| `POST extract` | tasks and team from a text by the LLM (WP6a with repair), for review |
| `GET simulator/instances`, `POST simulator`, `POST projects/{id}/advance` | simulator projects |

Errors: `{"error": {"code", "message", "details"}}` with 404/409/413/422/429/503; messages in
English or Polish (`?lang=pl`, `Accept-Language`). Demo mode (ADR-0024): signed session cookie,
showcase project, CSRF header on every state change, limits of `configs/app_demo.toml`, 24 h
expiry.

**References.** Kolisch 1996 (SGS fallback); Tarjan 1972 (cycles listed by name); Bertsekas,
Tsitsiklis & Wu 1997 (rollouts); Brooks 1995 (handover).
