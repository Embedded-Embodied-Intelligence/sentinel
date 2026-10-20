# WP2a — Stochastic simulator core (spec §2–§3)

<context>
You are the implementer of the Sentinel project. Read before coding:
- `CLAUDE.md`, `docs/spec/model.md` §1.2, §2, §3, §8, `docs/spec/architecture.md`
- `docs/reports/WP1.md`, `docs/notes/WP1.md`, `docs/adr/0006-*.md`
- skills `spec-guard`, `adr`, `wp-report`

This WP builds the "world" in which every later policy is evaluated: a day-by-day simulation of
a project with hidden stochastic durations and disruptions (D1 absences, D2 work increases,
D3 new activities). It must be exact, deterministic per seed, and fast, because WP3 and WP5 will
run it thousands of times per decision. Only the base policy `NoReaction` is implemented here;
richer policies come in WP4–WP5, so design the policy interface to be extended, not finished.

The architect has resolved the open semantics below. They are binding.
</context>

<task>
0. **Spec amendments (first, separate commit `spec: WP2 simulator semantics (v1.1)`).**
   Edit `docs/spec/model.md`: set the version to v1.1 and add the following, keeping existing
   numbering and adding §2.3 and §3.1:
   - §1.2: define `p̄_j := p_j · (a + 4m + b) / 6` (mean of the PERT multiplier), used for `B`.
   - §2.2 D1: `L` is geometric on {1, 2, …} with mean `E[L]` (numpy `geometric(p = 1/E[L])`);
     the announced bound is `L_low ~ Uniform{1, …, L}`. An absent worker is not drawn again
     until the day after their return.
   - §2.2 D2: the shock is indexed by the activity's own work-day counter (k-th day on which the
     activity progresses), not by calendar day; on a shock the hidden remaining work becomes
     `ceil(remaining · F)`.
   - §2.2 D3: template = duration and demands of a uniformly drawn real *original* activity;
     its true duration uses a pre-drawn PERT multiplier; successor `s` is uniform among
     unstarted real activities (the sink if none); predecessor is uniform among activities that
     are neither `s`, the sink, nor descendants of `s`. New ids are `n+2, n+3, …`; the sink
     keeps id `n+1`. If no valid predecessor exists, the event is skipped (logged).
   - new §2.3 Common random numbers: each replication seed spawns independent child streams
     (`numpy.random.SeedSequence.spawn`): (i) durations of original activities, (ii) one stream
     per worker for absences (one Bernoulli and, on onset, `L` and `L_low` draws per present
     day), (iii) one stream per original activity for D2 (one Bernoulli + factor per work-day),
     (iv) one stream for D3 (per calendar day: occurrence, template choice, PERT multiplier,
     two uniforms mapped onto the current candidate lists). Exogenous events that do not
     depend on the project state are therefore identical across policies for the same seed.
   - new §3.1 Execution details:
     (a) a paused activity releases its present workers, who may take other work; it resumes
         only when all its original workers are present and idle, unless the policy orders a
         substitution;
     (b) dispatch assigns the lowest-id idle present workers of each required role;
     (c) zero-duration activities complete inside dispatch, and dispatch repeats until no
         further activity can start on that day, so milestones add no delay;
     (d) an activity that progresses on days `S, …, S+P-1` finishes at `F = S + P`; its
         successors may start on day `F`;
     (e) under `NoReaction`, a D3 activity is added to the plan at the earliest
         precedence-feasible day `≥ t + 1` given current plan starts and realised finishes;
         no other plan entry changes;
     (f) the simulation ends when the sink completes, or at `max_days = ceil(5 · D)` (or
         `5 · Σ p_j` if `D` is undefined), with a `truncated` flag;
     (g) decision epochs: any day with a D1–D3 event, and every day `t` with `t % T_r == 0`.
   - Also update `.claude/skills/experiment-run/SKILL.md` Randomness section: "one seed per
     (instance, replication), shared by all methods (common random numbers)". And in the header
     of `model.md`, state that clarifications approved by the architect in a WP prompt do not
     need an ADR; semantic changes proposed by the implementer do.
1. **Uncertainty** `src/sentinel/simulation/uncertainty.py`: `PertParams(a=0.8, m=1.0, b=1.6,
   lam=4.0)`; `pert_multipliers(n, rng, params)` (Beta-PERT: `α = 1 + λ(m−a)/(b−a)`,
   `β = 1 + λ(b−m)/(b−a)`, `X = a + (b−a)·Beta(α, β)`; if `a == b` return the constant `a`
   without drawing); `realise_durations(instance, rng,
   params)` per §2.1 as amended; `expected_durations(instance, params)` = `p̄_j`;
   `derive_deadline(c_star, delta_d)` and `derive_budget(instance, beta, costs, params)` (§1.2).
2. **Disruptions** `src/sentinel/simulation/events.py`: `DisruptionParams(lambda_a, mean_absence,
   lambda_s, f_low=1.2, f_high=2.0, lambda_n)`; frozen event models `Absence`, `WorkIncrease`,
   `NewActivity`, each with `day`; a `ScenarioStreams` object built from `(seed, instance,
   params)` that owns the child generators of §2.3 and answers per-day queries from the engine.
   `DisruptionParams.none()` disables all events.
3. **State and observation** `src/sentinel/simulation/state.py`: mutable engine state (activity
   status `unstarted | running | paused | done`, work done `e_j`, hidden remaining work, assigned
   workers, realised start/finish; worker presence, true return day, announced bound, current
   assignment; plan; cost so far) and a frozen `Observation` that exposes only what the agent
   may see (§3): no true durations, no true absence lengths, no future events. Add a test that
   `Observation` carries none of the hidden fields.
4. **Policy interface** `src/sentinel/policies/base.py`: `Policy` protocol with
   `decide(observation) -> Decision`, where `Decision` currently holds a possibly empty list of
   operations; define only `Noop` now plus an extension point (a discriminated union to be
   extended in WP4). `src/sentinel/policies/no_reaction.py`: `NoReaction` always returns an
   empty decision.
5. **Engine** `src/sentinel/simulation/engine.py`:
   `simulate(instance, plan, policy, seed, *, pert, disruptions, deadline=None, review_period=5,
   costs=None, record_trace=False) -> SimulationResult`, implementing the six daily steps of §3
   with the §3.1 details. `SimulationResult`: realised starts/finishes for all activities
   (including inserted ones), makespan, `deadline_met`, total cost, number of decision epochs,
   event log, `truncated`, optional per-day trace. Costs: each worker-day of work costs `c_k`
   (default 1.0). Write the engine for speed (plain lists/ints in the inner loop, no pydantic
   objects per day); pydantic only at the boundaries.
6. **Tests** (unit, no network):
   - PERT: sample mean of 100 000 multipliers within 0.005 of `(a+4m+b)/6`; all in `[a, b]`.
   - Exact replay: with `pert` fixed to `X ≡ 1` (support `a = m = b = 1`) and no disruptions,
     simulating the CP-SAT optimal schedule of `tiny.sm` reproduces its starts exactly and
     makespan 7; same for the SGS-LFT schedule of a hand-made 8-activity instance.
   - Feasibility: with stochastic durations and no disruptions, the realised schedule passes
     `validate_schedule` on an instance whose durations are the realised `P_j`, and no activity
     starts before its planned start.
   - Determinism: same seed → identical `SimulationResult`; different seeds → different results
     on a non-trivial instance.
   - CRN: two different policies (use `NoReaction` and a test-only policy that only returns
     empty decisions but is a different class) give identical absence events for the same seed.
   - D1: a worker absent for `L` days pauses the activity, which resumes with the same worker
     after return; completed work is kept; announced bound ≤ true length.
   - D2: a forced shock (test hook or parameters with `lambda_s = 1`) increases the realised
     duration as `ceil(remaining · F)`.
   - D3: inserted activities keep the graph acyclic, get ids ≥ n+2, and the sink completes last.
   - Truncation: a run whose makespan necessarily exceeds `max_days` (e.g. a deadline set far
     below the critical path) ends with `truncated = True` at `max_days`.
   - `@pytest.mark.data`: 30 J30 instances × 5 seeds with default parameters run without errors;
     every realised schedule is feasible on its realised instance.
7. **Measurements** (report only): mean and p95 wall time of one `simulate` call on J30 and J60
   with default parameters (`lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02`,
   baseline plan = SGS-LFT), measured over at least 200 calls each.
8. Finish with the `wp-report` skill. In `docs/notes/WP2a.md` document the engine design, data
   structures and the CRN construction.
</task>

<constraints>
- Implement only `NoReaction`; no SUBST/RESEQ/OVERTIME logic yet, but the engine must already
  support resuming with original workers and must keep a clean hook where later operations will
  be applied (step 3 of §3).
- Do not change WP0/WP1 public interfaces except by adding functions.
- No new runtime dependencies (numpy is enough). No scipy.
- Hidden information never leaves the engine except through `SimulationResult` (for evaluation).
- If the spec amendments still leave a case undefined, use `spec-guard`.
- Commit after each completed step group (spec; uncertainty+events; engine+tests) so a partial
  session still leaves a consistent history.
</constraints>

<acceptance_criteria>
1. Spec commit present with all amendments; version v1.1.
2. Quality gate passes; `uv run pytest -q -m data` passes.
3. All tests listed in task 6 exist and pass.
4. Measured `simulate` timings for J30 and J60 reported (mean, p95). Target: J30 mean ≤ 5 ms,
   J60 mean ≤ 15 ms. If missed, profile, report the hotspots and a concrete optimisation plan
   (do not start a rewrite).
5. Report, notes, roadmap (WP2 → `in progress: WP2a done`) updated; pushed; tree clean.
</acceptance_criteria>

<report_format>
`docs/reports/WP2a.md` via the `wp-report` skill. "Numbers": timing table, test counts, mean
realised makespan / nominal makespan ratio on the 30×5 data run, number of events per type.
</report_format>
