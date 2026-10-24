# WP8 notes — project cockpit, release package, cache privacy for real data

**Cockpit (ADR-0021).** `sentinel dashboard` re-simulates one world of the studies and writes
one self-contained HTML page (inline CSS, hand-built inline SVG, about 50 lines of vanilla
JavaScript for tooltips, filtering and printing; no URL, no timestamp; 88–221 kB). The world is
that of `configs/wp5_rq4_main.toml` (base seed 2026, PERT(0.8, 1, 1.6) with λ = 4, E[L] = 3,
λ_S = 0.01, λ_N = 0.02, T_r = 5, T_cp = 0.1, β = 0.1, `cpsat_det` baseline plan), replication r
uses the WP2b seed, the policies are the WP4 baselines and the WP5 Sentinel variants with their
study parameters, so a study row is reproduced exactly (makespan, on time, hires, substitutions,
deliberations, escalations, approvals). Both policies run on the same seed (common random
numbers); Sentinel works towards D(δ_D), a baseline runs with the day limit of the studies'
largest slack, and on time is C ≤ D(δ_D) for both, as in the summaries.

**What the page shows.** Key figures of both policies (D, C, on time, cost / B, plan changes and
the planned starts they moved, temporary workers and their cost, substituted crew members,
escalations with approvals and deferrals, deliberations). The Gantt chart draws, per activity
with p_j > 0, the baseline plan over the realised execution: solid while the full crew worked,
striped while part of it was absent, an outline while paused (no crew member present), with
markers for substitutions, temporary workers, D2 shocks, D3 insertions and DESCOPE, and lanes of
the day's absences (crew members filled, idle workers hollow), work increases and new
activities. The risk chart is the agent's own forecast: at every deliberation NOOP's rollouts
are run again on the agent's sampled worlds (seed derive_seed(run seed, "sentinel", t), the
agent's rollout count), so P(C ≤ D) equals the decision record's and the same rollouts give the
P10, P50 and P90 of the makespan; the chosen action's p̂ is marked (filled triangle: applied at
once; hollow: deferred or escalated). A policy without forecasts gets the same estimate every
T_r days. The decision log has one row per deliberation and approval day: triggers (crew
absences and returns with their activity, idle absences counted, D2 of the previous day, D3,
review, approval day), the needs n_D / n_B, the choice and its level, the runner-up, p̂ / T̂ of
both, the deciding component and the gate outcome.

**Explanations.** The template text is built from the record alone (numbers as `render_record`
shows them: whole percentages of the two-decimal p̂, T̂ to one decimal of its two-decimal value,
the overrun as a percentage of its three-decimal value) and cites its facts in the role-3
schema, so the faithfulness check of spec §10.4 applies to it: every template of the test worlds
is fully faithful in English and in Polish (decimal commas read as points). With `--explain
ollama|openrouter` the deliberations that passed the needs gate get an LLM explanation through
the record/replay cache (`data/llm_cache/dashboard/`, settings of the RQ5 explanation study,
one seed per world, policy and day) with its check shown as a badge; no LLM was called in WP8.

**Example cockpits** (`docs/dashboard/`, Polish labels, λ_A = 0.01, rules in the README there):
J30 j3026_7 r1, Sentinel on time after 68 days (D = 68) where NoReaction needs 86, with 47
deliberations, 4 plan changes, 9 temporary workers and 1 substitution; J30 j301_9 r2, Sentinel
at autonomy 2 on time (57, D = 59) where NoReaction is one day late, with one deferred overtime
action, one SUBST escalated on day 50 and approved on day 51; J60 j6010_7 r1, Sentinel on time
(82, D = 83) with 19 temporary workers after P(on time) without action had fallen to 0 on day 10.

**Release.** `sentinel release --version 1.0.0`: `git archive` of HEAD, a generated
`RELEASE.md`, `--include` files under `docs/deliverables/`; refused for a dirty tree, another
version than `pyproject.toml`'s, `data/`, `.env*` other than `.env.example` (whose secret-like
variables must be empty), caches other than `results/<wp>/<run>/llm_cache.jsonl.gz`; entries
carry the commit time, so the zip is byte-identical for the same commit (16.9 MB, 476 files).

**Cache privacy for real data (spec v1.9.2 §10).** With `store_prompts = false` the client runs
the call's domain validator before the cache write; a schema-valid answer with domain issues is
stored, like an invalid one, only as issue kinds and masked locations, and returned as stored,
so a repair round sees only the kinds (event parser: per event index; WBS extraction: per
activity index, never a name). Research runs and committed bundles are unchanged, since the
validator is not part of the request key.
