# Sentinel — formal model (v1.3)

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
activities without demands (§3.1 a).

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

### §1.1 Mapping from PSPLIB

PSPLIB single-mode instances (`.sm`, parsed with `psplib.parse(path, instance_format="psplib")`)
provide `J, E, p, r, R_k`. Only single-mode instances with renewable resources are supported;
anything else is rejected with a clear error. Each capacity unit of role `k` is interpreted as
one worker `w = (k, i)`, `i = 0..R_k-1`, so that the absence of a specific person can be modelled.
Role names default to `R1..R|K|`; an optional display mapping to IT roles may be added later.
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

**Handover cost:** when SUBST (§4) replaces `m_j ≥ 1` absent members of activity `j`, `j` gets
additional work `h_j = max(1, ceil(α · e_j · m_j / M_j))` full-crew days, with crew size `M_j`
(§3.1 a); for a one-person activity this is `max(1, ceil(α · e_j))`.

**Cost:** each day, every *present* member of a running activity's crew costs `c_k` of its role
`k`; absent members cost nothing. Absences are therefore budget-neutral: they delay work but do
not add cost.

**State** `s_t`: day `t`; per activity status (done / running with `e_j` / paused with `e_j` /
unstarted); crews (assigned workers); worker availability with announced `L_low`; plan `π_t`;
cost so far; priors. **Hidden:** true `P_j`, true `L`, future events. Hidden quantities are
sampled from conditional distributions, e.g. `P_j | P_j > e_j`.

**Decision epochs:** after every D1–D3 event and every `T_r` days (periodic review); the exact
days are given in §3.1 (g).

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
- (g) Decision epochs: any day with a D1 or D3 event, the day after a D2 event (D2 is drawn in
  step 5, after the decision of its day), and every day `t` with `t % T_r == 0`.

---

## §4 Actions and permissions (WP4–WP5)

An action is a set of primitive operations; its permission level `ℓ(a)` is the maximum over
its operations.

| Operation | Effect | Cost | ℓ |
| --- | --- | --- | --- |
| `NOOP` | no change | — | 0 |
| `SHIFT(π')` | shift starts, same order, forecast makespan not increased | — | 0 |
| `RESEQ(π')` | repaired plan (CP-SAT or SGS), order may change | — | 1 |
| `SUBST(j, W')` | replace `m_j` absent members of a paused or running `j` by idle present workers `W'` of the same roles | `h_j` | 2 |
| `OVERTIME(k, u, H)` | `+u ≤ floor(γ R_k)` capacity of role `k` for `H` days | premium `c_OT_k` per unit-day | 2 |
| `DESCOPE(j)` | remove unstarted optional activity `j ∈ O` | value `v_j` | 2* |

SUBST applies to paused activities and to running activities with absent members. It replaces
`m_j ≥ 1` absent members by idle present workers of the same role, with handover cost
`h_j = max(1, ceil(α · e_j · m_j / M_j))` (§3). A replaced member who returns becomes idle and
leaves the crew; the substitute keeps the slot.

Levels: 0 automatic, 1 automatic with report, 2 human approval. `*` DESCOPE always needs
approval. Autonomy level `Λ ∈ {0,1,2,3}`: an action runs without approval iff `ℓ(a) < Λ` and
it contains no DESCOPE. A simulated human approves escalated actions after `δ_h` days.
Optional activities `O`: a random share `φ` of activities whose only successor is `n+1`, each
with value `v_j`. No classical crashing: adding people to a late software task is modelled by
the handover cost (Brooks's law).

---

## §5 Goals and needs (WP5)

For candidate `a`, run `N` rollouts with common seeds `ξ_1..ξ_N`, giving makespans `C_a^(i)`
and costs `Z_a^(i)`:

- `p̂_a = (1/N) Σ_i 1[C_a^(i) ≤ D]`
- `ẑ_a = (1/N) Σ_i Z_a^(i)`, `o_a = max(0, ẑ_a − B) / B`
- `Δ_a = (1/|U_t|) Σ_{j∈U_t} |S_j^a − S_j^t| + κ_h · n_a^subst` (`U_t` = unstarted activities)

Goal hierarchy: G1 feasibility (hard), G2 deadline `p̂ ≥ θ_D`, G3 budget `o = 0`,
G4 stability (small `Δ`).

**Needs** are evaluated for NOOP: `n_D = max(0, θ_D − p̂_NOOP)`, `n_B = o_NOOP`. If
`n_D ≤ ε_D` and `n_B ≤ ε_B`, the agent returns NOOP.

**Urgency** `τ_t = min_j (LS_j − t)` over unstarted and paused activities and running
activities with absent members (`LS_j` latest start w.r.t. `D`). If the best action needs approval and `τ_t > τ_def`, the decision is deferred.

---

## §6 Decision rule (WP5)

Sentinel is a one-step rollout policy (Bertsekas et al. 1997) on base policy `NoReaction`.
Rollouts continue without further interventions after the candidate action.

`a* = lexmax_{a ∈ C(s_t)} ( min(p̂_a, θ_D), −o_a, −Δ_a, −ℓ(a) )`

Differences in the first component smaller than two standard errors of the paired (CRN)
differences are ties. Scalarised ablation: `U_a = p̂_a − λ_B · o_a − λ_Δ · Δ_a`.

**Candidates** `C(s_t)`: rules (SHIFT; two RESEQ variants from CP-SAT: min makespan and min
deviation subject to makespan not worse than current; SUBST per paused activity, optionally
combined with RESEQ; OVERTIME for the most backlogged role; DESCOPE only if no other candidate
reaches `θ_D`) plus LLM proposals in the same JSON action grammar, filtered for feasibility.
Rollouts decode plans with the serial SGS.

---

## §7 Baseline policies (WP4)

- `NoReaction`: keep the plan; paused activities wait for their workers (rollout base policy).
- `AlwaysSubstitute`: replace every absent crew member (of paused and running activities)
  immediately when an idle present worker of the same role exists.
- `FullResolve`: after every disruption, CP-SAT re-solves for minimum makespan; handovers allowed.
- `StableResolve`: as FullResolve with a deviation penalty.

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
| `φ` | share of optional activities | 0.1 |
| `θ_D` | deadline probability target | 0.8 |
| `ε_D, ε_B` | need activation thresholds | 0.02, 0.01 |
| `κ_h` | handover weight in instability | 2 |
| `τ_def` | deferral urgency threshold (days) | 3 |
| `T_r` | periodic review (days) | 5 |
| `N` | rollouts per candidate | 200 |
| `Λ` | autonomy level | {0,1,2,3}, default 2 |
| `δ_h` | human approval delay (days) | 1 |
| `c_k` | daily cost per worker | 1.0 |

`λ_A` is per worker and day. A worker alternates between present spells of mean `1/λ_A` days
and absences of mean `E[L]`, so with `E[L] = 3`, `λ_A = 0.01` means about 3 % of worker-days
absent (`E[L] / (1/λ_A + E[L])`).

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
