# Sentinel — formal model (v2.0)

Source of truth for all semantics. Code must implement this document; changes require an ADR
and explicit approval (see `spec-guard` skill). Clarifications approved by the architect in a WP
prompt are entered directly and need no ADR; semantic changes proposed by the implementer do.
Section numbers are referenced by WP prompts.

Versions: v1.0 initial model; v1.1 (WP2a) simulator semantics: `p̄_j` (§1.2), D1–D3 details
(§2.2), common random numbers (§2.3), execution details (§3.1); v1.2 (WP2a.1) partial crews
(§3, §3.1 a), handover cost (§3), D2 timing (§2.2), early completion of zero-duration
activities (§3.1 c–d), accepted readings of the WP2a questions (§2.2), `λ_A` grid (§8); v1.3
(WP2b) answers to the WP2a.1 questions: decision epoch after D2 (§3, §3.1 g), SUBST for paused
and running activities with absent members (§4, §5, §7), cost of partial crews (§3),
activities without demands (§3.1 a); v1.4 (WP3a) beliefs and rollouts (§5.1), urgency of running
activities (§5), SUBST candidates and rollout CRN (§5.1, §6); v1.4.1 (WP3b) answers to the WP3a
questions: urgency of running activities regardless of absences (§5), empty absence support
(§5.1); forecast evaluation (§5.2); v1.4.2 (WP3b.1) forecast summaries: early warning
from `f ≥ 0.2`, plan-stage risk at `f = 0`, Brier skill score, AUC and PIT coverage (§5.2);
v1.5 (WP4a) interventions: SUBST details and RESEQ (§4), planning view and residual problem
(§4.1), the baseline policies made precise (§7), evaluation metrics (§7.1), `T_cp` (§8); v1.6
(WP4b) handover cost per newcomer (§3, §4), absence returns as decision epochs (§3, §3.1 g),
answers to the WP4a questions: replaced members (§4), handovers in the belief and the
deterministic forecaster (§5.1, §5.2), CP-SAT hint, FullResolve(subst) epochs and the deviation
set (§7, §7.1), `T_cp = 0.1` (§8); v1.7 (WP5a) Sentinel core: SHIFT and OVERTIME with temporary
workers (§4, §4.1), Δ over the deviation set and the needs gate (§5), candidates, racing
evaluation and deliberation epochs (§6), parameters (§8); the readings of the WP4b questions
(realised deviation over `J⁺`, return days without a crew) are accepted; v1.8 (WP5b) the
material decision rule with expected tardiness (§5, §6), the permission gate with deferral,
escalation and approval epochs (§3.1 g, §4, §6), DESCOPE and optional activities (§4, §6,
§7.1), `B`, `c_k` and `c_OT_k` in the observation (§3, §5), parameters (§8); answers to the
WP5a questions: SHIFT keeps the order strictly, overtime pay and cap (§4), needs-gate
sequencing (§5), racing of the scalarised ablation (§6); the rollout budget `(N₁, N) = (25, 100)`
of the WP5b study (§8); v1.8.1 (WP5b.1) answers to the WP5b questions: approved actions are
re-planned on their approval day, in the world and in rollouts (§4, §6), `O` is every real
activity whose only successor is the sink and `φ` is gone (§4, §8), deferred actions are not
remembered (§4), the paired standard error of `o` (§6), removed activities are not in `J⁺`
(§7.1); the racing leader (§6) and all-or-nothing approval (§4) as written in v1.8. v1.9
(WP6b) answers to the WP6a questions: extracted real activities have `p_j ≥ 1` (§1), the IT
role names (§1.1); the interpretation layer: team calendar, events from team messages, the
action grammar and its compilation, explanations (§10); v1.9.1 (WP6c) answers to the WP6b
questions: LLM calls never in the engine or a rollout, only by the agent at a deliberation of a
simulated world (§10), cache records without messages (`store_prompts = false`), mandatory for
real data (§10), "about N days" as an announced lower bound of N days (§10.2). v1.9.2 (WP8)
answers to the WP7 questions: with `store_prompts = false` an answer that fails its schema, and
a schema-valid answer with domain issues, are stored only as their issue lists, the domain
validator running before the cache write (§10). v2.0 (WP9a) live project mode: the calendar,
team, tasks and presets of a live project, its baseline plan, check-ins and their mapping to the
observation, forecasts, recommendations and decisions, and the simulator mode of the application
(§11); §1–§10 are unchanged.

Notation: indices are 0-based in code. Time is discrete, `t ∈ ℕ`, unit = one working day.

---

## §1 Project instance (static)

A project is `P = (J, E, K, W, p, r, D, B)`.

| Symbol | Meaning | Code |
| --- | --- | --- |
| `J = {0, …, n+1}` | activities; `0` = dummy start, `n+1` = dummy end, both duration 0 and demand 0 | `Activity.id: int` |
| `E ⊆ J × J` | finish-to-start precedences; the graph `(J, E)` is acyclic | `Activity.successors` |
| `K` | roles = renewable resource types (e.g. backend, frontend, QA, DevOps) | `Role` |
| `W` | workers; worker `w` has exactly one role `κ(w) ∈ K` | `Worker` |
| `R_k` | nominal capacity of role `k` = number of workers with that role | `Role.capacity` |
| `p_j ∈ ℕ` | nominal duration of activity `j` (days); `ℕ` includes 0, so a real activity may have `p_j = 0` (zero-duration milestone) | `Activity.duration` |
| `r_jk ∈ ℕ` | workers of role `k` required by activity `j` | `Activity.demands[k]` |
| `D` | deadline (§1.2) | `ProjectInstance.deadline` (optional) |
| `B` | budget (§1.2) | `ProjectInstance.budget` (optional) |

Validity conditions (enforced at construction):

- ids are exactly `0..n+1`; activity `0` has no predecessors, activity `n+1` has no successors;
- every activity is reachable from `0` and reaches `n+1`;
- the precedence graph is acyclic;
- `0 ≤ r_jk ≤ R_k` for all `j, k` (otherwise the instance is infeasible);
- dummies have `p = 0` and `r = 0`.

A project model extracted from a text description (RQ1, WP6a) gives every real activity a
duration `p_j ≥ 1`, as PSPLIB real activities have; zero-duration milestones are not extracted.

### §1.1 Mapping from PSPLIB

PSPLIB single-mode instances (`.sm`, parsed with `psplib.parse(path, instance_format="psplib")`)
provide `J, E, p, r, R_k`. Only single-mode instances with renewable resources are supported;
anything else is rejected with a clear error. Each capacity unit of role `k` is interpreted as
one worker `w = (k, i)`, `i = 0..R_k-1`, so that the absence of a specific person can be modelled.
Role names default to `R1..R|K|`. Texts for and from the LLM (RQ1, §10) display `R1–R4` as the
IT roles backend developer, frontend developer, tester and DevOps engineer.
Instance names follow the file stem with the set prefix, e.g. `j30/j301_1`.

### §1.2 Derived deadline and budget

PSPLIB defines neither. They are derived:

- `D = ceil((1 + δ_D) · C*)`, where `C*` is the optimal or best-known makespan of the
  deterministic instance (from PSPLIB solution files) and `δ_D` is the deadline slack.
- `B = (1 + β) · Σ_j Σ_k c_k · r_jk · p̄_j`, with daily cost `c_k` of a worker of role `k`
  (default 1.0) and `p̄_j := p_j · (a + 4m + b) / 6`, the nominal duration times the mean of
  the PERT multiplier of §2.1 (the rounding of §2.1 is ignored).

### §1.3 Static schedule

A schedule assigns start times `S_j`. Finish `F_j = S_j + p_j`. Makespan `C = S_{n+1}`.
A schedule is **feasible** iff:

1. precedence: `S_j ≥ F_i` for every `(i, j) ∈ E`;
2. resources: for every role `k` and every day `t`, `Σ_{j : S_j ≤ t < F_j} r_jk ≤ R_k`;
3. `S_0 = 0` and all `S_j ≥ 0`.

### §1.4 Bounds

`LB0` = length of the longest path from `0` to `n+1` with weights `p_j` (critical-path lower
bound, resources ignored). Earliest start times `ES_j` come from a forward pass; latest finish
times `LF_j` from a backward pass with horizon `T` (default `T = LB0` unless stated otherwise).

### §1.5 Benchmark metrics (WP1)

- deviation from reference: `dev_ref = 100 · (C − C_ref) / C_ref` [%], where `C_ref` is the
  optimum (J30) or best known upper bound (J60);
- deviation from critical path bound: `dev_lb0 = 100 · (C − LB0) / LB0` [%] (standard for J60+,
  Kolisch & Hartmann 2006);
- J30: share of instances where `C = C_opt`.

---

## §2 Uncertainty and disruptions (WP2+)

### §2.1 Durations

Actual duration `P_j = 0` if `p_j = 0` (dummies and zero-duration milestones), otherwise
`P_j = max(1, round(p_j · X_j))`, with `X_j ~ PERT(a, m, b) = (0.8, 1.0, 1.6)` (Beta-PERT, shape λ = 4; Malcolm et al. 1959).
`P_j` is **hidden**; the agent observes only work performed so far `e_j(t)` (in full-crew days,
§3.1 a).

### §2.2 Disruption events (each day, independently)

- **D1 absence:** each present worker becomes unavailable with probability `λ_A` for `L` days,
  where `L` is geometric on `{1, 2, …}` with mean `E[L]` (numpy `geometric(p = 1/E[L])`). The
  agent receives the announced lower bound `L_low ~ Uniform{1, …, L}` (e.g. "out until
  Friday"). True `L` is revealed on return. A worker absent on days `t, …, t+L−1` is back on
  day `t+L`; no Bernoulli is drawn on the return day, so draws resume on day `t+L+1`. Only
  availability is stored, never the reason.
- **D2 work increase:** on each of its work days (days with `ρ_j > 0`, §3.1 a), an activity has,
  with probability `λ_S`, its hidden remaining work (in full-crew days) replaced by
  `remaining · F` (no rounding), `F ~ U[f_low, f_high] = U[1.2, 2.0]`; the agent observes `F`.
  The Bernoulli of the k-th work day is drawn on that day before progress (step 5 of §3), so a
  one-day activity can be hit. The shock is indexed by the activity's own work-day counter `k`,
  not by calendar day. Activities inserted by D3 receive no work increases (documented
  simplification: §2.3 (iii) has streams for original activities only).
- **D3 new activity:** with probability `λ_N` a new activity is inserted. Template: the duration
  and demands of a uniformly drawn real *original* activity; its true duration uses a pre-drawn
  PERT multiplier (§2.1). Its successor `s` is uniform among unstarted real activities (the
  sink if none); its predecessor is uniform among activities that are neither `s`, the sink,
  nor descendants of `s`, the source and finished activities included, so insertion preserves
  acyclicity. New ids are `n+2, n+3, …`; the sink keeps id `n+1`. If no valid predecessor
  exists, the event is skipped (logged); since the source is always valid, this happens only
  for an instance without real activities.

### §2.3 Common random numbers

A replication is fully determined by a seed `ξ`. All compared policies receive the same `ξ`
(common random numbers). Each replication seed spawns independent child streams
(`numpy.random.SeedSequence.spawn`):

- (i) durations of original activities;
- (ii) one stream per worker for absences (one Bernoulli and, on onset, `L` and `L_low` draws
  per present day, the return day excepted);
- (iii) one stream per original activity for D2 (one Bernoulli + factor per work day, i.e. per
  day with `ρ_j > 0`);
- (iv) one stream for D3 (per calendar day: occurrence, template choice, PERT multiplier, two
  uniforms mapped onto the current candidate lists).

Exogenous events that do not depend on the project state are therefore identical across
policies for the same seed.

---

## §3 Execution semantics and state (WP2+)

A plan `π_t` gives a planned start `S_j` for every unstarted activity. Each day `t`:

1. realise D1 (returns, then new absences) and D3; D2 is realised in step 5 (§2.2);
2. **crews:** recompute `ρ_j` (§3.1 a) of every activity whose assigned workers' presence
   changed; an activity with `ρ_j = 0` is paused, a paused one with `ρ_j > 0` resumes with its
   own crew; completed work is kept (no voluntary preemption);
3. if `t` is a decision epoch, the policy decides;
4. **dispatch:** in order of `S_j`, start unstarted activities whose predecessors are complete,
   with `S_j ≤ t` and enough idle present workers of every required role. Activities with
   `p_j > 0` never start earlier than planned; zero-duration activities complete as soon as
   their predecessors are complete (§3.1 c–d);
5. **progress:** each running activity first draws its D2 shock for this work day (§2.2), then
   progresses by `ρ_j` full-crew days;
6. close activities whose remaining work is `≤ 0`.

**Handover cost** (onboarding per newcomer; Brooks 1995): when SUBST (§4) replaces `m_j ≥ 1`
absent members of activity `j`, each substitute needs `o_j = max(1, ceil(α · e_j))` crew-member
days of onboarding before contributing, `e_j` the work done so far in full-crew days (§3.1 a).
`j` gets additional work `m_j · o_j` crew-member days, i.e.
`h_j = m_j · o_j / M_j = m_j · max(1, ceil(α · e_j)) / M_j` full-crew days, with crew size `M_j`
(§3.1 a); for a one-person activity `h_j = max(1, ceil(α · e_j))`. Replacing a member thus saves
its crew work in expectation when the member's expected remaining absence exceeds `o_j` days.

**Cost:** each day, every *present* member of a running activity's crew costs `c_k` of its role
`k`; absent members cost nothing. Absences are therefore budget-neutral: they delay work but do
not add cost.

**State** `s_t`: day `t`; per activity status (done / running with `e_j` / paused with `e_j` /
unstarted / removed by DESCOPE, §4); crews (assigned workers); worker availability with
announced `L_low`; plan `π_t`; cost so far; priors. The observation also carries the budget `B`
(§1.2), the daily costs `c_k` and `c_OT_k` (§4) and the optional activities `O` (§4).
**Hidden:** true `P_j`, true `L`, future events. Hidden quantities are sampled from conditional
distributions, e.g. `P_j | P_j > e_j` (§5.1).

**Decision epochs:** after every D1–D3 event (absence onsets and returns included), every `T_r`
days (periodic review) and on the approval day of an escalated action (§4); the exact days are
given in §3.1 (g).

### §3.1 Execution details

- (a) **Partial crews.** An activity keeps all its assigned workers until it completes; nobody
  is released on absence, and assigned workers stay reserved (count against `R_k`) while
  absent. Work is measured in *full-crew days*: the remaining work of `j` starts at `P_j`, and
  on each day `j` runs it progresses by `ρ_j = present_assigned_j / M_j`, where
  `M_j = Σ_k r_jk` is its crew size and `present_assigned_j` the number of its assigned workers
  present that day. `e_j` is the work done so far in full-crew days. An activity with `M_j = 0`
  and `p_j > 0` progresses at rate `ρ_j = 1`. If `ρ_j = 0` (whole crew absent) the activity is
  paused; absent workers rejoin automatically on return unless SUBST replaced them (§4). Under
  `NoReaction` nobody is reassigned.
- (b) Dispatch assigns the lowest-id idle present workers of each required role.
- (c) Zero-duration activities (`p_j = 0`) complete inside dispatch as soon as all their
  predecessors are complete, whatever their planned start, and dispatch repeats until no
  further activity can start on that day, so milestones add no delay.
- (d) An activity finishes at the end of the first day on which its remaining work is `≤ 0`:
  if that day is `t`, `F_j = t + 1`, and its successors may start on day `F_j`. The railway rule
  "never start earlier than planned" applies only to activities with `p_j > 0`; zero-duration
  activities, the sink included, complete as soon as all predecessors are done, so a project
  can finish earlier than planned.
- (e) Under `NoReaction`, a D3 activity is added to the plan at the earliest precedence-feasible
  day `≥ t + 1` given current plan starts and realised finishes; no other plan entry changes.
- (f) The simulation ends when the sink completes, or at `max_days = ceil(5 · D)` (or
  `5 · Σ p_j` if `D` is undefined), with a `truncated` flag.
- (g) Decision epochs: any day with a D1 event (an absence onset or a return) or a D3 event, the
  day after a D2 event (D2 is drawn in step 5, after the decision of its day), every day `t`
  with `t % T_r == 0`, and the day `t + δ_h` on which the simulated human approves an action
  escalated on day `t` (§4 permission gate). A return day is an epoch whether or not the worker
  returns to a crew.

---

## §4 Actions and permissions (WP4–WP5)

An action is a set of primitive operations; its permission level `ℓ(a)` is the maximum over
its operations.

| Operation | Effect | Cost | ℓ |
| --- | --- | --- | --- |
| `NOOP` | no change | — | 0 |
| `SHIFT(π')` | order-preserving repair: re-time the unstarted activities, same order | — | 0 |
| `RESEQ(π')` | repaired plan (CP-SAT or SGS), order may change | — | 1 |
| `SUBST(j, W')` | replace `m_j` absent members of a paused or running `j` by idle present workers `W'` of the same roles | `h_j` | 2 |
| `OVERTIME(k, u, H)` | hire `u ≤ floor(γ R_k)` temporary workers of role `k` for the window `[t, t + H)` | `c_OT_k` per temporary worker and day while hired | 2 |
| `DESCOPE(j)` | remove unstarted optional activity `j ∈ O` | value `v_j` | 2* |

SUBST applies to paused activities and to running activities with absent members. It replaces
`m_j ≥ 1` absent members by idle present workers of the same role, with handover cost
`h_j = m_j · max(1, ceil(α · e_j)) / M_j` full-crew days, i.e. `o_j = max(1, ceil(α · e_j))`
crew-member days of onboarding per substitute (§3). An *idle* worker is present and in no crew.
SUBST(j, W') takes, per replaced member, an idle present worker of the same role; if a role has
more absent members than substitutes in `W'`, the substitutes, in the order given, replace its
absent members in increasing id order. The replaced member leaves the crew at once (on return
they are idle) and the substitute keeps the slot; `h_j` full-crew days (`m_j · o_j` crew-member
days) are added to `j`'s remaining work; `ρ_j` is recomputed immediately, so the new crew can
progress on the same day.

RESEQ(π') replaces the planned starts of all unstarted activities by a feasible solution of the
residual problem (§4.1). Dispatch semantics (§3 step 4) are unchanged.

SHIFT(π') is the order-preserving repair: the residual SGS (§4.1) with the current plan's planned
starts as priority list (ties by id). It may start activities earlier than the current plan
(left-justification under the railway rule) and never changes the order of planned starts:
every activity with `p_j > 0` starts no earlier than the one with `p_j > 0` before it in the
list, so a level-0 action never re-sequences.

OVERTIME(k, u, H) hires `u ≤ floor(γ R_k)` *temporary workers* of role `k` (overtime or agency
capacity), present every day of the window `[t, t + H)`, never absent, idle until assigned.
During the window they can be dispatched or used in SUBST like any idle worker (SUBST onboarding
applies; starting a new activity has no onboarding). A temporary worker assigned to a crew stays
until that activity completes; after the window it takes no new assignment and leaves when idle.
Cost `c_OT_k = 1.5 c_k` per temporary worker and day while hired (window days, plus any days
after the window while still in a crew); its crew work costs nothing on top, and window days
after the project ends are not paid. At most `floor(γ R_k)` temporary workers of a role are
hired at a time, those past their window but still in a crew included. Temporary workers have
ids after the original workers; they have no absence stream, so the common random numbers of
the original workers are unchanged (§2.3).

DESCOPE(j) removes an unstarted optional activity `j ∈ O` whose only successor is still `n+1`:
its precedence edges vanish, and a predecessor left without successors precedes `n+1` instead,
so the network stays valid (§1). A removed activity is never executed and costs nothing.
**Optional activities** `O` are all real activities whose only successor is the sink `n+1` in
the instance (three in every J30 and J60 instance), each with value `v_j = p_j · Σ_k c_k r_jk`.
The *scope loss* of a run is `Σ_removed v_j / Σ_{j∈O} v_j` (§7.1).

Operations are applied in step 3 in the order given, each validated against the state left by
the previous one; an invalid operation is rejected (logged, counted), the others still apply.

Levels: 0 automatic, 1 automatic with report, 2 human approval. `*` DESCOPE always needs
approval. No classical crashing: adding people to a late software task is modelled by the
handover cost (Brooks's law).

**Permission gate.** With autonomy level `Λ ∈ {0,1,2,3}`, an action other than NOOP runs
automatically iff `ℓ(a) < Λ` and it has no DESCOPE. Otherwise, if the urgency `τ_t > τ_def`
(§5), Sentinel *defers*: NOOP now, and it deliberates again at its next deliberation epoch (§6).
A deferred action is not remembered: every deliberation starts afresh, so the same action may
be chosen and deferred again until the urgency drops to `τ_def` and it is escalated.
Else it *escalates*: the simulated human approves after `δ_h` days, and day `t + δ_h` becomes a
decision epoch (§3.1 g). The human approves the *intent* of the action, not a schedule that may
be stale by then. On the approval day its SUBST, OVERTIME and DESCOPE operations are
re-validated, unchanged, against the current state, and its plan part is re-planned on the
current planning view (§4.1) left by them, with the objective of its candidate (§6): SHIFT is
recomputed, RESEQ-M minimises the residual makespan, RESEQ-S the deviation subject to the
residual makespan of the current SHIFT; the RESEQ-M of OT + RESEQ-M thus includes the temporary
workers. The action applies all or nothing: it is discarded, with a fresh deliberation, only if
a SUBST, OVERTIME or DESCOPE operation would be rejected or the re-plan fails, i.e. the engine
would reject the new plan (a CP-SAT stage without a solution falls back as in candidate
generation, which is no failure). Meanwhile Sentinel takes no other action. Deferrals,
escalations, approvals applied and approvals discarded are recorded.

### §4.1 Planning view

What a planner assumes at day `t`: the same assumptions as the deterministic forecaster of §5.2.

- Started activities (running or paused) keep their whole crew reserved until their *estimated
  finish* `F̂_j`, their finish in the deterministic forecast from the current observation.
- Absent idle workers are unavailable until their announced return (`s + L_low`, or `t + 1` if
  that has passed).
- Unstarted activities take their nominal duration `p_j` (inserted ones: their nominal
  duration).
- The capacity of role `k` on day `τ ≥ t` is `R_k` minus reserved crew members minus
  unavailable idle workers.
- Temporary workers (§4 OVERTIME) extend the view: each adds one unit of its role while it is
  hired, i.e. an idle one until the end of its window and one in a crew until the later of the
  window's end and its activity's `F̂_j`, during which its crew reserves it as above.

The **residual problem** schedules all unstarted activities on days `≥ t` under this capacity
profile and precedence (finished predecessors: realised finish; started ones: `F̂_j`); removed
activities (§4 DESCOPE) and their edges are no longer part of the project.

---

## §5 Goals and needs (WP5)

For candidate `a`, run `N` rollouts with common seeds `ξ_1..ξ_N`, giving makespans `C_a^(i)`
and costs `Z_a^(i)`:

- `p̂_a = (1/N) Σ_i 1[C_a^(i) ≤ D]`
- `T̂_a = (1/N) Σ_i max(0, C_a^(i) − D)`, the expected tardiness in days (a rollout cut at
  max_days counts `C = max_days`)
- `ẑ_a = (1/N) Σ_i Z_a^(i)`, the mean total project cost including the cost so far,
  `o_a = max(0, ẑ_a − B) / B` with the budget `B` of the observation
- `Δ_a = (1/|U'_t|) Σ_{j∈U'_t} |S_j^a − S_j^t| + κ_h · n_a^subst`: the candidate's plan `S^a`
  against the current plan `S^t` over the deviation set `U'_t` of §7.1, plus `κ_h` per member
  the candidate replaces (`n_a^subst`, §7.1 substitutions)

Goal hierarchy: G1 feasibility (hard), G2 deadline `p̂ ≥ θ_D`, and small expected tardiness
`T̂` where `θ_D` is out of reach, G3 budget `o = 0`, G4 stability (small `Δ`).

**Needs** are evaluated for NOOP: `n_D = max(0, θ_D − p̂_NOOP)`, `n_B = o_NOOP`. **Needs
gate:** NOOP is evaluated first on `N₁` rollouts; the gate stops there only if they show a need
beyond 2 standard errors (`θ_D − p̂ − ε_D` above 2 standard errors of `p̂`, or the overrun of the
mean cost lowered by 2 standard errors above `ε_B`), otherwise NOOP is extended to `N` rollouts;
if `n_D ≤ ε_D` and `n_B ≤ ε_B` on those, the agent returns NOOP without generating candidates.

**Urgency** `τ_t = min_j τ_j` with `τ_j = LS_j − t` for unstarted and paused activities and
`τ_j = LF_j − t − E[remaining_j]` for running activities regardless of absences, the
expectation under the belief of §5.1 (`LS_j`, `LF_j` latest start and finish w.r.t. `D`). If
the chosen action needs approval and `τ_t > τ_def`, it is deferred (§4 permission gate).

### §5.1 Beliefs

The rollouts of §5 start from a state sampled from the belief given the observation of day `t`.

- **Durations.** The pmf of `P_j` is the distribution of the sampler of §2.1: `P_j = 0` if
  `p_j = 0`, else `max(1, round(p_j · X))`, `X ~ PERT` (ties have probability zero). Work is
  measured in full-crew days (§3.1 a), `e_j` included. For an activity with observed work `e_j`
  and shocks `(e_1, F_1), …, (e_m, F_m)` (work done at each shock, factor), the belief samples
  `P_j` from this pmf conditioned on the activity not being finished: with `R_0 = P_j`,
  `R_i = (R_{i−1} − (e_i − e_{i−1})) · F_i` (`e_0 = 0`), require `R_i > 0` for all shocks and
  current remaining `R_m − (e_j − e_m) > 0`; the sampled remaining work is that last value.
  SUBST handovers `(e_i, h_i)` (work done at the handover, `h_j` of §3) are replayed with the
  shocks in order of work done, a handover before a shock at equal work (step 3 precedes step
  5): `R_i = R_{i−1} − (e_i − e_{i−1}) + h_i`, requiring `R_{i−1} − (e_i − e_{i−1}) > 0` (the
  activity had not finished before the handover).
  Unstarted original activities sample `P_j` from the unconditional pmf; inserted activities use
  their nominal duration as `p_j`.
- **Absences.** For an absent worker with absence start `s`, announced bound `L_low` and today
  `t`, the posterior of `L` is `∝ q(1−q)^{L−1} · (1/L)` (geometric prior with `q = 1/E[L]`,
  likelihood of a uniform announcement) on `L ≥ max(L_low, t − s + 1)`, truncated at
  `L ≤ 365`. The worker returns on day `s + L`. If no `L` in that range has positive
  probability (`max(L_low, t − s + 1) > 365`, or `E[L] = 1` while `L ≥ 2` is required), the
  belief takes the smallest admissible length `L = max(L_low, t − s + 1)` and counts a fallback.
- **Future.** Disruptions after day `t` follow the priors of §2.2 with fresh random numbers.
- **Rollout.** From a sampled state, the remaining project is simulated with the base policy
  `NoReaction` (§6) exactly by the engine semantics of §3 and §3.1.
- **Rollout CRN.** Rollout `i` uses seed `ξ_i` for both the belief sample and the future, so
  every candidate sees the same `N` sampled worlds.

### §5.2 Forecast evaluation (WP3b)

Forecasts of the makespan `C` of a NoReaction run are scored against its realised value (RQ3).

- **Checkpoints.** The world executes the baseline plan (makespan `C_plan`) under NoReaction.
  At step 3 of day `t_f = floor(f · C_plan)`, `f ∈ {0, 0.2, 0.4, 0.6, 0.8}`, each forecaster
  receives the observation and its current plan only; `C` is used after the forecast is
  returned. A checkpoint with `C ≤ t_f` (project complete by day `t_f`) is skipped. Recording
  observations does not change the run.
- **Forecasters.** All forecasters of one checkpoint use the same forecast seed (CRN).
  - `mc_full`: the forecaster of §5.1 with `N = 200` rollouts.
  - `mc_no_future`: the same without disruptions after day `t_f` (belief about the current
    hidden state only).
  - `deterministic` (plan-based estimate of classical PM tools): one NoReaction run from the
    observation with nominal hidden values and no disruptions after day `t_f`. Unstarted
    activities (inserted ones included) have remaining work `p_j`. A started activity has
    remaining work that starts at `p_j`, decreases by the work done, never falls below one
    crew-member day `1/M_j`, and is multiplied by `F` at each observed D2 shock:
    `R_0 = p_j`, `R_i = max(R_{i−1} − (e_i − e_{i−1}), 1/M_j) · F_i`,
    `R = max(R_m − (e_j − e_m), 1/M_j)`; without shocks `max(p_j − e_j, 1/M_j)`. SUBST
    handovers are replayed with the shocks in the order of §5.1 and add `h_j` after the floor:
    `R_i = max(R_{i−1} − (e_i − e_{i−1}), 1/M_j) + h_i`. An absent worker returns on day
    `s + max(L_low, t − s + 1)`: after the announced bound, or tomorrow if the bound has passed.
    Its point forecast `Ĉ` is a point-mass distribution, so `P(C ≤ D) = 1[Ĉ ≤ D]`.
  - Misspecified priors: `mc_full` with the rates `(λ_A, λ_S, λ_N)` of its future multiplied
    by `κ`, or with another PERT `(a, m, b)` in its belief and future, while the world keeps
    the true parameters.
- **Binary forecasts.** Per forecast, `p = P̂(C ≤ D)` and `y = 1[C ≤ D]` (a truncated run is
  late), for `δ_D ∈ {0.2, 0.3}` from the same samples. Over `N` forecasts, with `K = 10` bins
  `[k/10, (k+1)/10)` (the last one closed), `n_k` forecasts in bin `k`, their mean `p̄_k`,
  their outcome frequency `ȳ_k` and the overall frequency `ȳ`:
  - Brier score `BS = (1/N) Σ (p − y)²` (Brier 1950); `REL = (1/N) Σ_k n_k (p̄_k − ȳ_k)²`,
    `RES = (1/N) Σ_k n_k (ȳ_k − ȳ)²`, `UNC = ȳ(1 − ȳ)`, so `BS = REL − RES + UNC` up to the
    within-bin term (binning error, reported separately; Murphy 1973);
  - `ECE = Σ_k (n_k / N) |p̄_k − ȳ_k|`; sharpness `(1/N) Σ (p − p̄)²`; log score
    `−(1/N) Σ [y ln p' + (1 − y) ln(1 − p')]` with `p' = min(max(p, 0.005), 0.995)` (lower
    is better);
  - Brier skill score `BSS = 1 − BS / UNC` (Murphy 1988): the reference is the constant
    forecast `ȳ`, whose Brier score is `UNC`. `ȳ` is the base rate of the same `N` forecasts
    (same set, `f` and `λ_A` cell), so the reference is in-sample: it knows the frequency that
    the forecaster has to estimate. `BSS = 1` for perfect forecasts, 0 for the base rate,
    negative below it; undefined if `UNC = 0`;
  - AUC (area under the ROC curve) of `p` for separating on-time from late forecasts, in the
    Mann–Whitney form `AUC = (1/(N_1 N_0)) Σ_{i: y_i = 1} Σ_{j: y_j = 0} (1[p_i > p_j] +
    ½ · 1[p_i = p_j])` with `N_1` on-time and `N_0` late forecasts (ties count ½; Hanley &
    McNeil 1982). 0.5 is no discrimination; AUC ignores calibration; undefined if `N_1 = 0` or
    `N_0 = 0`.
- **Makespan distribution.** `F` is the empirical CDF of the samples `x_1, …, x_n` (a point
  mass for `deterministic`), `q_α` the smallest `x` with `F(x) ≥ α`:
  - `CRPS = (1/n) Σ_i |x_i − C| − (1/(2n²)) Σ_i Σ_k |x_i − x_k|`, the CRPS of `F` (Gneiting &
    Raftery 2007); a point mass gives `|Ĉ − C|`. Reported as `CRPS / C*`, with
    `MAE / C* = |q_0.5 − C| / C*`;
  - quantile coverage `1[q_0.1 ≤ C ≤ q_0.9]` of the central 80 % interval. It over-covers an
    integer `C`: both bounds enter with their whole probability mass, and `F(q_0.9) ≥ 0.9`,
    `F(q_0.1 − 1) < 0.1`, so a calibrated forecast covers `C` with probability
    `F(q_0.9) − F(q_0.1 − 1) > 0.8`, the more so the more concentrated `F` is;
  - randomised PIT `u = F(C − 1) + V · (F(C) − F(C − 1))`, `V ~ U(0, 1)`, uniform for a
    calibrated forecast of an integer quantity (Czado et al. 2009), shown with 10 equal bins;
  - PIT coverage of the central 80 % interval: the share of forecasts with `u ∈ [0.1, 0.9]`,
    exactly 0.8 for a calibrated forecast, so it is the exact check of that interval.
- **Early warning** with threshold `θ ∈ {0.5, 0.8}`: a run is warned if `p < θ` at some
  non-skipped checkpoint with `f ≥ 0.2`, first on day `t_w`. Among late runs: the share warned
  and the mean lead time `D − t_w` of the warned ones; among on-time runs: the share warned
  (false alarms). The checkpoint `f = 0` does not count: before execution has revealed any
  deviation, a calibrated forecaster reports roughly the base rate, which is below `θ` for
  nearly every run when most runs are late. That is plan-stage risk, not early warning.
- **Plan-stage risk** with the same `θ`: the share of runs with `p < θ` at `f = 0`, among late
  runs and among on-time runs, reported separately from early warning.
- **Uncertainty.** 95 % percentile intervals from a cluster bootstrap over instances (1,000
  resamples, fixed seed; instances are drawn with replacement within each set and every row of
  a drawn instance enters the statistic). Every statistic, BSS and AUC included, is recomputed
  from the rows of each resample. Paired differences between forecasters use the same
  resamples.

---

## §6 Decision rule (WP5)

Sentinel is a one-step rollout policy (Bertsekas et al. 1997) on base policy `NoReaction`.
Rollouts continue without further interventions after the candidate action.

`a* = lexmax_{a ∈ C(s_t)} ( min(p̂_a, θ_D), −T̂_a, −o_a, −Δ_a, −ℓ(a) )`

with the expected tardiness `T̂_a` of §5. Every component decides only on differences that are
statistically and practically material. Two candidates **tie** in a stochastic component
(`min(p̂, θ_D)`, `T̂`, `o`) when their paired (CRN) difference is within 2 paired standard errors
**or** below its materiality threshold: `ε_D` for `min(p̂, θ_D)`, `ε_T` for `T̂`, `ε_B` for `o`.
They tie in `Δ` when the difference is below `ε_Δ`, and in `ℓ` only when equal. The paired
standard error is that of the mean of the per-rollout differences over the `N` common rollouts:
of the on-time indicators for `min(p̂, θ_D)`, of the tardiness `max(0, C − D)` for `T̂`, and of
the total cost divided by `B` for `o` (exact where both candidates are over budget, conservative
where `o` is clipped at 0). The best set is filtered component by component: keep
every candidate tied with the best of the current set (among equal values the first in candidate
order), then move to the next component; the remaining ties go to the candidate order below.
With DESCOPE candidates, the scope loss of a candidate (`v_j / Σ_{i∈O} v_i` of the activity it
removes, 0 for every other candidate) is an extra component right after `T̂` (smaller first,
exact), so a DESCOPE wins only when it is materially better in `min(p̂, θ_D)` or `T̂`.
Scalarised ablation: `U_a = p̂_a − λ_B · o_a − λ_Δ · Δ_a`, maximised over the candidates that
racing keeps (racing as below).

**Candidates** `C(s_t)`, at most these, each filtered for validity:
- `NOOP`;
- `SHIFT` (§4);
- `RESEQ-M`: CP-SAT, minimum residual makespan;
- `RESEQ-S`: minimum deviation subject to residual makespan ≤ that of SHIFT;
- `SUBST(j)` for the up to 3 most urgent eligible activities (paused, or running with absent
  members, §4; urgency `τ_j` of §5);
- `SUBST-ALL`: every eligible substitution, in the order of AlwaysSubstitute (§7);
- `SUBST-ALL + RESEQ-M`;
- `OT(k*) + RESEQ-M`, with `k*` the most backlogged role, `u = floor(γ R_k*)`, `H = 2 T_r`; the
  backlog of role `k` is `Σ r_jk · p_j / R_k` over the unstarted and paused activities with
  `LS_j ≤ t + 2 T_r` (nominal durations);
- `DESCOPE(j)`, only where DESCOPE is enabled, for up to 2 unstarted optional activities
  `j ∈ O` whose only successor is `n+1`, those with the largest `p_j` (ties: smaller `v_j`,
  then id), generated only if no other candidate reaches `θ_D` (`p̂_a ≥ θ_D` after racing), and
  then raced with the others on the same worlds. DESCOPE is off in the main RQ4 comparison,
  since the baselines cannot descope.

RESEQ plans with added capacity use the planning view extended by the temporary workers (§4.1).
LLM proposals in the action grammar of §10.3, compiled and filtered for validity, extend this
list (WP6).

**Evaluation.** Each candidate is applied at step 3 of day `t` in every rollout; the rollout then
continues under NoReaction (§5.1; rollout `i` uses seed `ξ_i`, shared by all candidates). A
candidate that would need approval (§4 permission gate) is instead approved at step 3 of day
`t + δ_h` exactly as in the world: its plan part is re-planned on that rollout's planning view of
the day and its other operations are re-validated, all or nothing, so the agent imagines the
approval delay and the re-plan; a discarded candidate leaves the rollout to continue without
it.
**Racing:** stage 1 evaluates every candidate on `N₁` rollouts; a candidate is dropped only if
it is significantly and materially worse than the stage's best in `min(p̂, θ_D)` **and** in
`T̂`, i.e. not tied with it in either component (ties as above, on the `N₁` rollouts); the
stage's best is the candidate with the largest `min(p̂, θ_D)`, then the smallest `T̂`, then the
first in candidate order. Stage 2 extends the survivors to `N` rollouts, on which the rule
decides; `ẑ` and `Δ` are those of §5.

**Deliberation epochs.** Sentinel deliberates at decision epochs that have an event touching a
crew (absence onset or return of a crew member, D2, D3) and at periodic epochs; at epochs whose
only events concern idle workers it returns NOOP. While an escalated action awaits approval it
returns NOOP without deliberating; on the approval day it applies the re-planned action, or
deliberates afresh if the action is discarded (§4 permission gate). This is the agent's own
choice of when to think; the approval days are the only decision epochs it adds (§3.1 g).

---

## §7 Baseline policies (WP4)

- `NoReaction`: keep the plan; paused activities wait for their workers (rollout base policy).
- `AlwaysSubstitute`: at every decision epoch, for paused and running activities with absent
  members, in increasing `τ_j` (§5 urgency, ties by id), substitute every absent member for
  which an idle present worker of the same role exists (lowest ids first). Plan unchanged.
- `FullResolve(subst)`: at every decision epoch that has a D1 (onset or return), D2 or D3 event
  (not purely periodic epochs): if `subst`, first the SUBST operations of `AlwaysSubstitute`;
  then RESEQ with minimum residual makespan. FullResolve(subst) thus substitutes at these event
  epochs only, AlwaysSubstitute at every epoch.
- `StableResolve(subst)`: as FullResolve, but RESEQ is lexicographic: stage 1 minimum residual
  makespan `C₁`; stage 2 minimum `Σ_{j ∈ U'_t} |S_j − S_j^t|` subject to makespan `≤ C₁`
  (Van de Vonder et al. 2007 style robust repair). `S_j^t` is the current plan and `U'_t` the
  *deviation set*: the unstarted activities with `p_j > 0` that were not inserted on day `t`
  (milestones, the sink and D3 activities of the current day are excluded).
- CP-SAT in policies: 1 worker, fixed seed, deterministic limit `T_cp` per stage. The solution
  hint is the whole current plan if it is a feasible solution of the residual problem within
  the CP-SAT horizon (the makespan of the residual SGS with LFT priority), else the residual SGS
  schedule; there are no partial hints. If no feasible solution is found within the limit,
  fall back to the residual SGS with LFT priority and count it.

### §7.1 Evaluation metrics (WP4b, WP7)

- on-time for each `δ_D`, makespan / `C*`, cost / `B`;
- *realised deviation* `(1/|J⁺|) Σ_{j ∈ J⁺} |S_j^real − S_j^0|` against the baseline plan, over
  `J⁺`, the original activities with `p_j > 0` (milestones and the dummies are excluded as in
  the deviation set of §7; D3 activities have no baseline start; activities removed by DESCOPE
  never start and are left out);
- *nervousness* = total number of pairs (epoch `t`, activity `j ∈ U'_t`) whose planned start the
  decision of epoch `t` changed (`U'_t` the deviation set of §7);
- number of substitutions (replaced members), onboarding days `Σ m_j o_j` (crew-member days) and
  handover days `Σ h_j` (full-crew days); number of RESEQs and CP-SAT fallbacks;
- overtime cost and its share of the total cost, temporary workers hired (§4 OVERTIME); scope
  loss `Σ_removed v_j / Σ_{j∈O} v_j` (§4 DESCOPE); deferrals, escalations, approvals applied and
  approvals discarded (§4 permission gate).

---

## §8 Parameters and defaults

| Symbol | Meaning | Default |
| --- | --- | --- |
| `δ_D` | deadline slack vs `C*` | {0.1, 0.2, 0.3} |
| `β` | budget reserve | 0.10 |
| `(a, m, b)` | PERT multiplier | (0.8, 1.0, 1.6) |
| `λ_A` | daily absence probability per worker | {0.0025, 0.005, 0.01, 0.02} |
| `E[L]` | mean absence length (days) | {3, 5} |
| `λ_S` | daily work-increase probability per running activity | 0.01 |
| `λ_N` | daily new-activity probability | 0.02 |
| `α` | handover factor | 0.3 |
| `γ` | overtime cap vs `R_k` | 0.2 |
| `θ_D` | deadline probability target | 0.8 |
| `ε_D, ε_B` | need activation thresholds (§5) and materiality of `min(p̂, θ_D)` and `o` (§6) | 0.02, 0.01 |
| `ε_T` | materiality of the expected tardiness `T̂` (§6) | 0.5 days |
| `ε_Δ` | materiality of the instability `Δ` (§6) | 0.5 days |
| `κ_h` | handover weight in instability | 2 |
| `τ_def` | deferral urgency threshold (days) | 3 |
| `T_r` | periodic review (days) | 5 |
| `T_cp` | CP-SAT deterministic time limit per stage in policies (§7) | 0.1 deterministic seconds |
| `N` | rollouts per candidate | 100 |
| `N₁` | rollouts per candidate in stage 1 of racing (§6) | 25 |
| `c_OT_k` | daily cost of a temporary worker of role `k` (§4) | `1.5 c_k` |
| `H` | OVERTIME window of the rule candidate (§6) | `2 T_r` |
| — | single-activity SUBST candidates (§6) | at most 3 |
| — | DESCOPE candidates (§6) | at most 2 |
| `Λ` | autonomy level | {0,1,2,3}, default 2 |
| `δ_h` | human approval delay (days) | 1 |
| `c_k` | daily cost per worker | 1.0 |

`λ_A` is per worker and day. A worker alternates between present spells of mean `1/λ_A` days
and absences of mean `E[L]`, so with `E[L] = 3`, `λ_A = 0.01` means about 3 % of worker-days
absent (`E[L] / (1/λ_A + E[L])`).

The rollout budget `(N₁, N) = (25, 100)` comes from the WP5b study
(`scripts/bench_rollout_budget.py`): on 722 deliberations of 10 J30 and 5 J60 Sentinel runs at
`λ_A = 0.01`, its choice agreed with the choice on all candidates over `N = 800` common worlds
in 90.3 % of the deliberations and lost on average 0.0014 in `p̂` and 0.023 days in `T̂` of the
reference statistics (adoption limits 0.01 and 0.25 days); `(50, 200)` agreed in 92.2 %
(0.0008, 0.018 days) with twice the rollouts (909 against 462 per deliberation).

---

## §9 References

- Kolisch & Sprecher 1997 — PSPLIB, EJOR 96(1). doi:10.1016/S0377-2217(96)00170-1
- Kolisch 1996 — serial/parallel SGS, EJOR 90(2). doi:10.1016/0377-2217(95)00357-6
- Kolisch & Hartmann 2006 — heuristics update, EJOR 174(1). doi:10.1016/j.ejor.2005.01.065
- Herroelen & Leus 2005 — scheduling under uncertainty, EJOR 165(2). doi:10.1016/j.ejor.2004.04.002
- Van de Vonder et al. 2007 — predictive-reactive procedures, J. Sched. 10(3). doi:10.1007/s10951-007-0011-2
- Bertsekas, Tsitsiklis & Wu 1997 — rollout algorithms, J. Heuristics 3(3). doi:10.1023/A:1009635226865
- Simon 1955 — satisficing, QJE 69(1). doi:10.2307/1884852
- Malcolm et al. 1959 — PERT, Oper. Res. 7(5). doi:10.1287/opre.7.5.646
- Brooks 1995 — The Mythical Man-Month, Addison-Wesley.
- Brier 1950 — probability forecast verification, Mon. Weather Rev. 78(1). doi:10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2
- Murphy 1973 — vector partition of the probability score, J. Appl. Meteorol. 12(4). doi:10.1175/1520-0450(1973)012<0595:ANVPOT>2.0.CO;2
- Gneiting & Raftery 2007 — strictly proper scoring rules, JASA 102(477). doi:10.1198/016214506000001437
- Czado, Gneiting & Held 2009 — predictive model assessment for count data, Biometrics 65(4). doi:10.1111/j.1541-0420.2009.01191.x
- Murphy 1988 — skill scores based on the mean square error, Mon. Weather Rev. 116(12). doi:10.1175/1520-0493(1988)116<2417:SSBOTM>2.0.CO;2
- Hanley & McNeil 1982 — area under the ROC curve, Radiology 143(1). doi:10.1148/radiology.143.1.7063747

---

## §10 Interpretation layer (WP6)

The LLM has three roles: it turns team messages into events (§10.2), proposes candidate actions
in a fixed grammar (§10.3) and explains decisions (§10.4). **LLM output enters the decision
layer only as validated, compiled objects:** events after validation, applied to the
observation by code; proposals compiled into candidates, which the rollouts evaluate and the
rule of §6 chooses among; explanations never enter it. **No LLM call is made inside the engine
(the simulator of §2–§3) or inside a rollout.** In a simulated world only the agent may call the
LLM, at a deliberation (the online check of RQ5: proposals at the deliberations that passed the
needs gate); the rollouts that evaluate its proposals make no call. Every call goes through the
record/replay cache with a JSON-schema-validated answer. Prompts and texts are in English.

**Cache records and privacy.** A cache record holds the request key (the SHA-256 of the full
request: backend, model, weights digest, messages, schema and decoding parameters), the model
metadata (backend, model, digest, schema name and hash, decoding parameters, the serving
provider) and the response. With `store_prompts = true` it also holds the messages; with
`store_prompts = false` it holds no message text, and record and replay work by the key alone.
`store_prompts = false` is mandatory for real (non-synthetic) data, in the working cache and in
every replay bundle (invariant 7, GDPR Art. 9); research runs on synthetic messages and
fictional rosters keep the full records.
With `store_prompts = false`, an answer that fails its schema is stored only as its issue list
(error kind, and per violation its type and location, with names outside the schema masked);
the client returns it as stored. In that mode a call with a domain validator (the event parser
of §10.2, the WBS extraction of RQ1) runs it before the cache write, and a schema-valid answer
with domain issues is likewise stored only as its issue list (per issue its kind and location,
never a value of the answer) and returned as stored, so that a repair round sees only the issue
kinds. A free-text field (a worker's name such as "Ada K. (flu)") therefore never reaches the
cache unless the answer passes its validator. Research runs (`store_prompts = true`) are
unchanged.

### §10.1 Team calendar

Day 0 is a Monday. The working days are Monday to Friday, without holidays; one simulation day
is one working day, so day `t` is weekday `t mod 5` (0 Monday, …, 4 Friday) of week `⌊t/5⌋`. A
message is dated by its day and weekday. In a message of day `t`, "on <weekday>" names the first
day after `t` with that weekday (1–5 days later) and "next week" names the Monday `5(⌊t/5⌋ + 1)`.

### §10.2 Events from team messages (role 1)

A message of day `t` comes from a member of the team roster, which gives every original worker
a unique first name next to its role. The parser answers `{"events": [...]}`, an empty list for
a message without an event (meeting moves, praise, questions); a message may report several:

- `{"type": "absence", "worker": w, "return_day": r}`: worker `w` is absent from day `t` on
  (a D1 onset); `r` is the announced earliest return day, so `L_low = r − t`, or `null` if the
  message gives none (`L_low = 1`). A weekday gives `r` by §10.1, "about N days" an announced
  lower bound of N days, `r = t + N`, "next week" the Monday of the next week.
- `{"type": "work_increase", "activity": j, "factor": F}`: the remaining work of the running
  activity `j` is multiplied by `F ≥ 1` (D2, observed with the current `e_j`). "About x % more"
  gives `F = 1 + x/100`, "twice as long" `F = 2`, "another d days" `F = (r_j + d) / r_j` with
  `r_j` the remaining work shown to the parser (the deterministic estimate of §5.2 in full-crew
  days, one decimal); `F` has two decimals.
- `{"type": "new_activity", "name": ..., "duration": p, "crew": {role: n}, "after": i,
  "before": s}`: a D3 activity with nominal duration `p ≥ 1` and `n` workers per role, inserted
  as `i → new → s`; `i = null` is the source ("can start right away") and `s = null` the sink
  ("before the release"). As in §2.2, `s` is an unstarted real activity or the sink and `i` is
  neither `s`, the sink, a descendant of `s` nor removed; `n ≤ R_k`.

No field can hold the reason for an absence (invariant 7, GDPR Art. 9): a reason in a message
is dropped. **Validation** lists the issues of an answer: unknown or already absent workers,
return days `≤ t` or `> t + 365`, unknown activities, work increases of activities that are not
running, `F < 1`, new activities with `p < 1`, unknown roles, crews above `R_k`, a name in use or
an invalid placement, and a worker or activity named twice. As in RQ1, up to three repair rounds
send the previous answer and its issues back; events with issues after the last round are
dropped. **Application:** the accepted events change the observation of day `t` as the engine
would: an absent worker gets `present = false`, `absent_since = t` and `announced = L_low`, and
a running activity left without a present crew member is paused; a work increase appends
`(j, e_j, F)` to the observed shocks; a new activity gets the next id, status unstarted and the
planned start of §3.1 (e).

### §10.3 Action grammar (role 2)

An answer holds at most three proposals, a proposal at most three operations:

- `{"op": "SHIFT"}` and `{"op": "RESEQ", "objective": "makespan" | "stable"}`: SHIFT of §4 and
  RESEQ-M or RESEQ-S of §6 (`stable`: minimum deviation within the makespan of SHIFT);
- `{"op": "SUBST", "activity": j}`: SUBST of the paused or running `j` for every absent member
  for which an idle present worker of its role is left, in the order of AlwaysSubstitute (§7):
  absent members in increasing id order, the lowest-id idle workers first;
- `{"op": "OVERTIME", "role": k, "workers": u, "days": H}`: OVERTIME(k, u, H) of §4 with
  `1 ≤ u ≤ ⌊γ R_k⌋` and `1 ≤ H ≤ 20`.

DESCOPE is not part of the grammar. **Compilation** (code): a proposal has at most one plan
operation (SHIFT or RESEQ). Its other operations apply in the order given, each validated on the
state the previous ones leave; a SUBST chooses its substitutes there, so the temporary workers of
an earlier OVERTIME may substitute. The plan operation is then planned on the state they leave,
whatever its place in the list, exactly as for the rule candidates (CP-SAT plans for RESEQ on the
planning view with the temporary workers, §4.1, §6). A proposal with an operation the engine
would reject, two plan operations, an ineligible SUBST, an unknown role or activity or a
parameter out of range compiles to an issue instead of a candidate. Its level is `ℓ(a)` of §4.
A compiled proposal with the effect of a rule candidate or of an earlier proposal (equal
operations other than SHIFT and RESEQ and equal planned starts of the activities with
`p_j > 0`) is a duplicate and is not evaluated. The others join `C(s_t)` after the rule
candidates, in answer order, are raced and chosen by §6 like them, and behind the permission gate
are approved and re-planned (§4) with the objective of their plan operation.

### §10.4 Explanations (role 3)

From the `DecisionRecord` of a deliberation that passed the needs gate, the LLM writes
`{"summary": text, "cited_facts": [{"kind": k, "value": v}]}`: a summary of at most 80 words for
a project manager and the facts it uses, `k ∈ {chosen_action, p_on_time, tardiness_days,
budget_overrun, alternative, alternative_p_on_time, deciding_component}` (the chosen candidate's
label, `p̂`, `T̂` and `o`; the runner-up's label and `p̂`; the rule component that decided, the
record's reason). **Faithfulness:** every cited fact equals the record's value (numbers within
the rounding of the value written; probabilities and the overrun as fractions or percentages);
the chosen action is cited; the deciding component is cited and right; every number written in
digits in the summary matches a value of the record shown to the LLM within its rounding, else
it counts as a hallucinated number. An explanation that passes all four checks is fully
faithful.

---

## §11 Live project mode (WP9)

The application runs the decision layer on a real project that a project manager updates at
check-ins (*project mode*) and on a generated one with a hidden world (*simulator mode*). It adds
no semantics to §1–§10: this section maps what the manager enters onto the instance (§1), the
plan and the observation (§3), and the decisions of Sentinel (§4–§6) back onto the project.

### §11.1 Calendar

A project has a start date `d₀`. Working days are Monday to Friday without holidays (§10.1);
model day `t` is the `t`-th working day on or after `d₀` (`t = 0` the first), `date(t)` its
calendar date, and every date shown to users is a calendar date. For a date `d`, `first(d)` is
the day of the first working day on or after `d` and `last(d)` that of the last working day on
or before `d` (`−1` before `date(0)`).

- A task that starts on date `s` has `S_j = first(s)`; one whose last day of work is `f` has
  `F_j = last(f) + 1` (§3.1 d). A start `S_j` is shown as `date(S_j)`, a finish `F_j` as the
  date of its last day of work, `date(F_j − 1)`.
- The deadline is a date `d_D` by the end of which all work is done: `D = last(d_D) + 1`. A
  makespan `C` (§1.3) is shown as the finish date `date(C − 1)`, so `C ≤ D` iff that date is not
  after `d_D`.
- A check-in dated `d` reports the state at the end of `d`: it is the observation of step 3 of
  day `t = last(d) + 1` (`t = 0` for a date before `date(0)`), and what it leads to applies from
  day `t` on. Check-ins come in date order; a later one on the same day `t` updates it.

### §11.2 Team, tasks and settings

- **Team.** People with a display name (unique) and a role. Role names are free text, matched as
  in the WBS extraction (case, spacing and a final plural *s* ignored), and a project has any
  number of roles. The capacity `R_k` of role `k` is its number of people (§1); its daily cost
  `c_k` per person defaults to 1.0, a *cost unit*. Roles get the ids `0, 1, …` in the order of
  their first person, people the worker ids `0, 1, …` in the order listed, so the dispatch rule
  (§3.1 b) prefers people listed first.
- **Tasks.** A name (unique), the estimated duration `p_j ≥ 1` in working days, the crew `r_jk`
  per role (people needed, possibly none, §3.1 a), the predecessors (finish-to-start) and an
  optional flag. Tasks get the activity ids `1, …, n` in the order listed; the source precedes
  the tasks without predecessors and the sink follows those without successors (§1). The
  optional tasks form `O` (§4); an optional task is no task's predecessor.
- **Presets.** The estimation-uncertainty preset sets the PERT multiplier (§2.1, `λ = 4`):
  `confident` (0.9, 1, 1.3), `typical` (0.8, 1, 1.6, the research default) or `uncertain`
  (0.7, 1, 2.0). The disruption-rate preset sets `λ_A` (§2.2): `calm` 0.005, `typical` 0.01 or
  `turbulent` 0.02, with `λ_S = 0.01`, `λ_N = 0.02` and `E[L] = 3`. Every value can be changed
  in the advanced settings.
- **Goals.** The deadline is a date (§11.1), the budget `B` is in cost units, by default that of
  §1.2 with `β = 0.1` and the preset's PERT mean. `P(C ≤ D)` and recommendations need a
  deadline.
- **Validation** reports in plain language, in English or Polish: an empty or repeated name, an
  unknown predecessor, dependency cycles listed by task name, a duration below one day, a crew
  above the team size of a role (`r_jk > R_k`), an unknown role, an optional task that other
  tasks depend on, a project without tasks, and a deadline before the critical path
  (`D < LB0`, §1.4) with the earliest possible finish date.
- **Structure.** The team, the tasks, their estimates, crews and dependencies can change until
  the first check-in, and a change asks for a new baseline plan. From then on the plan's
  structure changes only through check-ins (new tasks, more work, §11.3) and actions (§11.5);
  names, the deadline, the budget and the settings can always change.

### §11.3 Baseline plan and check-ins

- **Baseline plan** `π⁰`: CP-SAT on the instance with one worker, a fixed seed and the
  deterministic limit `T_cp` (§8), or the serial SGS with the LFT rule (§7; Kolisch 1996) if
  CP-SAT finds no plan, checked by `validate_schedule` (§1.3). Tracking needs a baseline plan.
- **Check-in** dated `d` (day `t`, §11.1): per task one of *not started*, *in progress* with the
  share done `x ∈ [0, 1)` or *done* with its finish date, each started task optionally with its
  start date and its crew; reported absences (person, first day, announced return date or none;
  never a reason, invariant 7); work increases of tasks in progress (`+N` working days or a
  factor `×F`); new tasks (fields of §11.2, inserted after one task `i` and before one task `s`
  as in §10.2). Tasks not mentioned keep their state; a started task does not become unstarted
  again, nor a done task undone.
- **Mapping to the `Observation`** of day `t` (§3); everything not listed is as in the engine:
  - *Starts and finishes.* A done task has `S_j < F_j ≤ t`, a started one `S_j < t`; without a
    start date `S_j` is the planned start, clamped to the days since the previous check-in and
    before the finish. A task starts only once its predecessors are done (`S_j ≥ F_i`).
  - *Work done* in full-crew days: `e_j = x · p_j · ΠF`, with `ΠF` the product of the factors
    reported for the task at earlier check-ins, rounded half up to whole crew-member days
    (`e_j · max(1, M_j)` an integer, §3.1 a); a done task has `e_j = p_j · ΠF`. The share refers
    to the task's own work, so SUBST onboarding (§3) stays in the remaining work.
  - *Crews.* A crew is assigned at the start day by the rule of §3.1 (b): the lowest-id idle
    present workers of each role, the tasks started since the previous check-in taken in order
    of start day, planned start and id, a crew being reserved from `S_j` to `F_j`. The manager
    may name the crew instead (people of the right roles in no crew reserved on `S_j`); if no
    crew can be assigned, the check-in says so and asks for one.
  - *Status.* A started, unfinished task is *running* if a crew member is present on day `t` or
    it has no crew, else *paused* (§3.1 a).
  - *Absences.* A person absent from `s = first(a)` with announced return date `r` is back on
    day `first(r)`, so `L_low = first(r) − s ≥ 1` (§2.2); without a return date `L_low = 1`
    (§10.2) and the absence lasts until a check-in gives its return date. The person is absent
    on day `t` iff an absence covers `t`: `present = false`, `absent_since = s` and
    `announced = L_low`. An absence that starts after `t` waits for a later check-in.
  - *Work increases.* `×F` with `F > 1` is used as given; `+N` working days (`N > 0`) gives
    `F = (R + N) / R`, with `R` the deterministic remaining work of §5.2 in full-crew days after
    the check-in's progress. The shock `(j, e_j, F)` is appended to the observed shocks (§3).
  - *New tasks* get the next ids `n + 2, …`, status unstarted and the planned start of §3.1 (e).
  - *Cost so far*: the work done of every started task, `e_j` full-crew days at the daily cost of
    its crew's people (temporary workers excluded), plus the pay `c_OT_k` of each temporary
    worker for the days it was hired before `t` (§4).
  - *Plan*: the current planned starts; the observation also reports `D`, `B`, `c_k`,
    `c_OT_k = 1.5 c_k`, `O` and the presets (§3).

### §11.4 Forecasts

The forecast of day `t` runs `N = 200` NoReaction rollouts (§5.1) from the latest observation and
its plan, with the seed `derive_seed(project seed, "forecast", t)`: `P(C ≤ D)`, the finish dates
of the 10 %, 50 % and 90 % quantiles of `C` (§5.2), and the *risk drivers*, the tasks most often
on the critical chain of a rollout. The critical chain of a completed rollout holds the
activities from which tight links lead to the sink: `i → j` is tight if `i` is a predecessor of
`j` with `F_i = S_j`, or, for a `j` without such a predecessor, if `F_i = S_j` and `i` and `j`
need a common role. A risk driver's share is the fraction of rollouts whose chain holds it.

### §11.5 Recommendations and decisions

- A **recommendation** is a Sentinel deliberation (§5–§6) on the observation of the latest
  check-in (`t = 0` before the first), with the seed `derive_seed(project seed, "sentinel", t)`,
  the rule candidates (the LLM proposals of §10.3 are off by default), DESCOPE candidates if the
  project has optional tasks, and the parameters of §8. One follows every check-in; the manager
  may ask for one at any time. It shows the chosen action in plain language, its effect against
  NOOP (`p̂`, the expected finish date `date(C̄ − 1)` with `C̄` the mean makespan of its
  rollouts rounded half up, the expected cost `ẑ`, the plan changes), the runner-up and the
  explanation of §10.4.
- **Autonomy.** `Λ` is a project setting (default 2, §8). A chosen action other than NOOP with
  `ℓ(a) < Λ` and without DESCOPE is applied at once and listed as applied automatically. Any
  other chosen action waits for the manager, who takes the place of the simulated human of §4:
  there is no deferral and no approval delay `δ_h`; the urgency `τ_t` (§5) is shown, and an
  action with `τ_t > τ_def` *can wait*.
- **Approve** applies the action to the current observation as on an approval day (§4): its
  SUBST, OVERTIME and DESCOPE operations unchanged and re-validated, its plan part planned again
  on the planning view they leave, all or nothing. The project then has the new plan, the named
  substitutes in the crews (the replaced members leave them, §4), the temporary workers
  "Temporary <role> 1, 2, …" hired from that day for `H` days (§4 OVERTIME) and the removed
  optional task. An action that is no longer valid is discarded with its reason, and a fresh
  recommendation follows. **Reject** records the rejection; **later** leaves the recommendation
  open until the next check-in or recommendation replaces it.
- Every definition change, baseline plan, check-in, recommendation and decision is an event of
  the project's append-only log, from which the project is rebuilt deterministically.

### §11.6 Simulator mode

A simulator project is a PSPLIB instance (§1.1) shown with the IT role names, the narrator's task
names (WP6a) and a roster of people (§10.2), a calendar start date, the presets of §11.2, the
deadline `D = ceil((1 + δ_D) C*)` (§1.2; `C*` the reference makespan, else that of the baseline
plan) and the budget of §1.2. A seed fixes its hidden world (§2.3). `advance(n)` executes the
next `n` days of the engine (§3) on that world from the baseline plan under the chosen policy:
Sentinel at autonomy `Λ` with the simulated human of §4, NoReaction or a policy of §7. Advanced
to the end, the run equals `simulate` with the same plan, policy and seed. NoReaction is advanced
on the same seed for a side-by-side comparison (common random numbers, §2.3).
