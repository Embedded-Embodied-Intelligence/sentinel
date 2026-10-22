"""Rule candidates C(s_t) of Sentinel (spec section 6), each filtered for validity.

`generate` returns, in this order and at most: NOOP; SHIFT, the order-preserving repair;
RESEQ-M, CP-SAT for minimum residual makespan; RESEQ-S, CP-SAT for minimum deviation within
SHIFT's makespan; SUBST(j) for the up to three most urgent eligible activities; SUBST-ALL in
the order of AlwaysSubstitute; SUBST-ALL + RESEQ-M; OT(k*) + RESEQ-M for the most backlogged
role (not in the `no_overtime` variant). `prepare` builds each: the operations other than RESEQ
and SHIFT are rehearsed through the engine's own `Run.apply` on the observed state, and the plan
part of its kind (`PLAN_PARTS`) is planned on the state they leave, so a RESEQ with added
capacity sees the planning view extended by the temporary workers, and checked there as the
engine checks plans. A candidate is dropped if anything would be rejected, or if its effect
(operations other than RESEQ and SHIFT, and the planned starts it leaves for activities with
p_j > 0) equals that of an earlier candidate. `approve` builds an escalated candidate again in
the same way on its approval day (spec section 4 permission gate), in the world and in
rollouts. `descopes` gives the DESCOPE candidates, which the agent adds only if no other
candidate reaches theta_D (spec section 6).
"""

import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.agent.params import SentinelParams
from sentinel.model.schedule import Schedule
from sentinel.policies.always_substitute import substitutions
from sentinel.policies.base import Decision, Descope, Operation, Overtime, Reseq, Shift, Subst
from sentinel.policies.urgency import latest_finishes, urgencies
from sentinel.scheduling.cpsat import solve_residual
from sentinel.scheduling.residual import ResidualProblem, planning_view, shift_sgs
from sentinel.simulation.engine import plan_rejection, rehearse
from sentinel.simulation.state import (
    PAUSED,
    RUNNING,
    UNSTARTED,
    Observation,
    nominal_activity,
    overtime_cap,
    successor_lists,
    worker_roles,
)

CandidateKind = Literal[
    "noop",
    "shift",
    "reseq_m",
    "reseq_s",
    "subst",
    "subst_all",
    "subst_all_reseq_m",
    "ot_reseq_m",
    "descope",
]
KINDS: tuple[CandidateKind, ...] = (
    "noop",
    "shift",
    "reseq_m",
    "reseq_s",
    "subst",
    "subst_all",
    "subst_all_reseq_m",
    "ot_reseq_m",
    "descope",
)
PlanObjective = Literal["shift", "makespan", "deviation"]
# The plan part of each kind of candidate (spec section 6), planned on the state its other
# operations leave, again on the approval day of an escalated action (spec section 4); the
# other kinds have none.
PLAN_PARTS: dict[CandidateKind, PlanObjective] = {
    "shift": "shift",
    "reseq_m": "makespan",
    "reseq_s": "deviation",
    "subst_all_reseq_m": "makespan",
    "ot_reseq_m": "makespan",
}


class Candidate(BaseModel):
    """A candidate action: its `decision`, the planned starts of all activities it leaves
    (`plan`, for the instability Delta of spec section 5), the crew members it replaces, its
    scope loss v_j / sum_O v_i (DESCOPE, spec section 6) and the CP-SAT stages that fell back
    while planning it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    kind: CandidateKind
    decision: Decision
    plan: tuple[int, ...]
    substituted: NonNegativeInt
    scope_loss: NonNegativeFloat = 0.0
    fallbacks: NonNegativeInt = 0

    @property
    def level(self) -> int:
        """l(a), the permission level of spec section 4."""
        return self.decision.level


class Generation(BaseModel):
    """The candidates of one epoch and the effort: CP-SAT searches, their fallbacks and wall
    time, candidates dropped as invalid or as duplicates, and the wall time of `generate`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[Candidate, ...]
    solves: NonNegativeInt
    fallbacks: NonNegativeInt
    solve_time_s: NonNegativeFloat
    invalid: NonNegativeInt
    duplicates: NonNegativeInt
    wall_time_s: NonNegativeFloat


def noop(observation: Observation) -> Candidate:
    """NOOP: keep everything (level 0)."""
    return Candidate(
        label="NOOP", kind="noop", decision=Decision(), plan=observation.plan, substituted=0
    )


def generate(
    observation: Observation, plan: Schedule | None = None, params: SentinelParams | None = None
) -> Generation:
    """The rule candidates of the observed epoch (spec section 6), NOOP first.

    `plan` is the current plan (default: the observation's), against which RESEQ-S minimises
    the deviation over the deviation set. Every candidate is built by `prepare`.
    """
    began = time.perf_counter()
    params = SentinelParams() if params is None else params
    if plan is not None:
        observation = observation.model_copy(update={"plan": plan.starts})
    builder = _Builder(observation, params)
    builder.add(noop(observation))
    builder.offer("SHIFT", "shift")
    builder.offer("RESEQ-M", "reseq_m")
    builder.offer("RESEQ-S", "reseq_s")
    for op in single_substitutions(observation)[: params.max_single_subst]:
        builder.offer(f"SUBST({op.activity})", "subst", (op,))
    every = substitutions(observation)
    if every:
        builder.offer("SUBST-ALL", "subst_all", every)
        builder.offer("SUBST-ALL+RESEQ-M", "subst_all_reseq_m", every)
    if params.variant != "no_overtime":
        role = most_backlogged_role(observation, 2 * params.review_period)
        if role is not None:
            workers = overtime_cap(observation.instance.roles[role].capacity)
            if workers > 0:
                hire = Overtime(role=role, workers=workers, days=params.window)
                builder.offer(f"OT({role})+RESEQ-M", "ot_reseq_m", (hire,))
    return Generation(
        candidates=tuple(builder.candidates),
        solves=builder.solves,
        fallbacks=builder.fallbacks,
        solve_time_s=builder.solve_time_s,
        invalid=builder.invalid,
        duplicates=builder.duplicates,
        wall_time_s=time.perf_counter() - began,
    )


@dataclass(frozen=True)
class PlanPart:
    """A plan part computed on a planning view (`plan_part`): the RESEQ or SHIFT operation, why
    the engine would reject it on that view (None: valid), the CP-SAT searches run, the stages
    that fell back and the solver's wall time."""

    operation: Reseq | Shift
    rejection: str | None
    solves: int
    fallbacks: int
    solve_time_s: float


# Plan parts by objective and planning view: a plan part depends on nothing else, so the
# rollouts of one epoch can share those of their approval days (spec section 6 evaluation).
PlanCache = dict[tuple[object, ...], PlanPart]


def plan_part(view: ResidualProblem, objective: PlanObjective, params: SentinelParams) -> PlanPart:
    """The plan part of a candidate on the planning view `view` (spec section 6), checked on
    it as the engine checks plans (`plan_rejection`): "shift" is SHIFT, the order-preserving
    repair; "makespan" RESEQ-M by CP-SAT for minimum residual makespan, hinted as in spec
    section 7; "deviation" RESEQ-S by CP-SAT for minimum deviation within SHIFT's makespan,
    hinted with the SHIFT plan, a feasible solution of that makespan, to which it falls back.
    CP-SAT runs with T_cp per stage, one worker and `cp_seed`, so the part is a function of
    `view` alone."""
    if objective == "shift":
        operation: Reseq | Shift = Shift(starts=shift_sgs(view))
        solves = fallbacks = 0
        solve_time_s = 0.0
    else:
        if objective == "makespan":
            hint, bound = view.planned_starts(), None
        else:
            hint = shift_sgs(view)
            bound = hint[view.sink]
        solution = solve_residual(
            view,
            objective,
            deterministic_time_limit=params.deterministic_time_limit,
            seed=params.cp_seed,
            hint=hint,
            bound=bound,
        )
        operation = Reseq(starts=solution.starts)
        solves, fallbacks, solve_time_s = 1, solution.fallbacks, solution.wall_time_s
    return PlanPart(operation, plan_rejection(view, operation), solves, fallbacks, solve_time_s)


@dataclass(frozen=True)
class Prepared:
    """An action built on an observation (`prepare`): the `decision`, the observation it leaves
    (`after`), why the engine would reject it (`rejection`; None: valid) and the effort of its
    plan part: CP-SAT searches run, stages that fell back, the solver's wall time, and whether
    the part came from a cache (`reused`, then without effort)."""

    decision: Decision
    after: Observation
    rejection: str | None
    solves: int = 0
    fallbacks: int = 0
    solve_time_s: float = 0.0
    reused: bool = False


def prepare(
    observation: Observation,
    kind: CandidateKind,
    operations: tuple[Operation, ...] = (),
    params: SentinelParams | None = None,
    plans: PlanCache | None = None,
) -> Prepared:
    """The action of a candidate of `kind` with `operations` (no RESEQ or SHIFT) on the observed
    state (spec sections 4 and 6). The operations are rehearsed through the engine (`rehearse`);
    if none is rejected and the kind has a plan part (`PLAN_PARTS`), that part is planned on the
    planning view of the state they leave and checked there (`plan_part`), and the action leaves
    that state with the new plan. `plans`, if given, holds plan parts by objective and planning
    view and is used and filled."""
    params = SentinelParams() if params is None else params
    decision = Decision(operations=operations)
    objective = PLAN_PARTS.get(kind)
    after = observation
    if operations or objective is None:
        after, rejected = rehearse(observation, decision, handover_factor=params.handover_factor)
        if rejected:
            return Prepared(decision, after, rejected[0].reason)
        if objective is None:
            return Prepared(decision, after, None)
    view = planning_view(after)
    key = (objective, *(getattr(view, name) for name in ResidualProblem.model_fields))
    part = None if plans is None else plans.get(key)
    reused = part is not None
    if part is None:
        part = plan_part(view, objective, params)
        if plans is not None:
            plans[key] = part
    decision = Decision(operations=(*operations, part.operation))
    if part.rejection is None:  # the engine sets the planned starts of the plan (`Run.apply`)
        starts = part.operation.starts
        plan = tuple(starts.get(j, day) for j, day in enumerate(after.plan))
        after = after.model_copy(update={"plan": plan})
    if reused:
        return Prepared(decision, after, part.rejection, reused=True)
    return Prepared(decision, after, part.rejection, part.solves, part.fallbacks, part.solve_time_s)


def approve(
    observation: Observation,
    candidate: Candidate,
    params: SentinelParams | None = None,
    plans: PlanCache | None = None,
) -> Prepared:
    """The action of an escalated candidate on its approval day (spec section 4 permission
    gate): its SUBST, OVERTIME and DESCOPE operations unchanged, re-validated on the observed
    state, and its plan part planned again on the planning view they leave, with its kind's
    objective (`prepare`). It applies all or nothing: only if `rejection` is None. Sentinel uses
    it on the approval day, and so do the rollouts that imagine the approval (spec section 6)."""
    operations = tuple(
        op for op in candidate.decision.operations if not isinstance(op, Reseq | Shift)
    )
    return prepare(observation, candidate.kind, operations, params, plans)


class _Builder:
    """Collects valid, distinct candidates and counts the CP-SAT effort. Two candidates have
    the same effect if their operations other than RESEQ and SHIFT are equal and so are the
    planned starts they leave for activities with p_j > 0: dispatch ignores the planned starts
    of zero-duration activities (spec section 3.1 c)."""

    def __init__(self, observation: Observation, params: SentinelParams) -> None:
        self.observation = observation
        self.params = params
        self.timed = [
            nominal_activity(observation, j)[0] > 0 for j in range(len(observation.status))
        ]
        self.candidates: list[Candidate] = []
        self.effects: set[tuple[str, tuple[int, ...]]] = set()
        self.solves = self.fallbacks = self.invalid = self.duplicates = 0
        self.solve_time_s = 0.0

    def offer(
        self,
        label: str,
        kind: CandidateKind,
        operations: tuple[Operation, ...] = (),
        *,
        scope_loss: float = 0.0,
    ) -> None:
        """Build the candidate with `prepare`; keep it if nothing would be rejected and its
        effect is new."""
        prepared = prepare(self.observation, kind, operations, self.params)
        self.solves += prepared.solves
        self.fallbacks += prepared.fallbacks
        self.solve_time_s += prepared.solve_time_s
        if prepared.rejection is not None:
            self.invalid += 1
            return
        substituted = sum(len(op.workers) for op in operations if isinstance(op, Subst))
        self.add(
            Candidate(
                label=label,
                kind=kind,
                decision=prepared.decision,
                plan=prepared.after.plan,
                substituted=substituted,
                scope_loss=scope_loss,
                fallbacks=prepared.fallbacks,
            )
        )

    def add(self, candidate: Candidate) -> None:
        others = tuple(
            op for op in candidate.decision.operations if not isinstance(op, Reseq | Shift)
        )
        plan = tuple(
            day if timed else -1 for day, timed in zip(candidate.plan, self.timed, strict=True)
        )
        effect = (Decision(operations=others).model_dump_json(), plan)
        if effect in self.effects:
            self.duplicates += 1
            return
        self.effects.add(effect)
        self.candidates.append(candidate)


def optional_values(observation: Observation) -> dict[int, float]:
    """v_j = p_j sum_k c_k r_jk of every optional activity j in O (spec section 4), with the
    observation's daily costs c_k (1.0 if it has none)."""
    costs = observation.costs or (1.0,) * len(observation.instance.roles)
    values: dict[int, float] = {}
    for j in observation.optional:
        duration, demands = nominal_activity(observation, j)
        values[j] = duration * sum(c * r for c, r in zip(costs, demands, strict=True))
    return values


def descopes(observation: Observation, params: SentinelParams | None = None) -> list[Candidate]:
    """DESCOPE(j) for up to `max_descope` unstarted optional activities whose only successor is
    the sink, those with the largest p_j (ties: smaller v_j, then id; spec section 6), each
    rehearsed through the engine and with its scope loss v_j / sum_O v_i."""
    params = SentinelParams() if params is None else params
    values = optional_values(observation)
    total = sum(values.values())
    sink = observation.instance.sink_id
    successors = successor_lists(observation)
    eligible = [j for j in values if observation.status[j] == UNSTARTED and successors[j] == [sink]]
    eligible.sort(key=lambda j: (-nominal_activity(observation, j)[0], values[j], j))
    builder = _Builder(observation, params)
    for j in eligible[: params.max_descope]:
        loss = values[j] / total if total > 0 else 0.0
        builder.offer(f"DESCOPE({j})", "descope", (Descope(activity=j),), scope_loss=loss)
    return builder.candidates


def single_substitutions(observation: Observation) -> list[Subst]:
    """SUBST(j) for every eligible activity, most urgent first (tau_j of spec section 5, ties by
    id): j is paused, or running with absent members, and an idle present worker of an absent
    member's role exists. Each replaces j's absent members in increasing id order by the
    lowest-id idle workers of their roles, as AlwaysSubstitute would for j alone (spec 7)."""
    status, present, assigned = observation.status, observation.present, observation.assigned
    roles = worker_roles(observation)
    busy = {w for j, state in enumerate(status) if state in (RUNNING, PAUSED) for w in assigned[j]}
    idle: dict[int, list[int]] = {}  # role -> idle present workers, increasing ids
    for w, here in enumerate(present):
        if here and w not in busy:
            idle.setdefault(roles[w], []).append(w)
    found: dict[int, Subst] = {}
    for j, state in enumerate(status):
        if state not in (RUNNING, PAUSED):
            continue
        taken: dict[int, int] = {}  # role -> substitutes used
        chosen: list[int] = []
        for w in sorted(assigned[j]):
            pool = idle.get(roles[w], [])
            used = taken.get(roles[w], 0)
            if not present[w] and used < len(pool):
                chosen.append(pool[used])
                taken[roles[w]] = used + 1
        if chosen:
            found[j] = Subst(activity=j, workers=tuple(chosen))
    if len(found) > 1:
        tau = urgencies(observation, found)
        return [found[j] for j in sorted(found, key=lambda j: (tau[j], j))]
    return list(found.values())


def most_backlogged_role(observation: Observation, horizon: int) -> int | None:
    """k* of the OVERTIME candidate (spec section 6): the role with the largest backlog
    sum_j r_jk p_j / R_k over the unstarted and paused activities with LS_j <= t + `horizon`
    (nominal durations, LS_j = LF_j - p_j for the deadline D, else the planned makespan); ties
    by smallest id, None if every backlog is zero."""
    t = observation.day
    deadline = observation.deadline
    sink = observation.instance.sink_id
    latest = latest_finishes(observation, observation.plan[sink] if deadline is None else deadline)
    capacities = [role.capacity for role in observation.instance.roles]
    backlog = [0.0] * len(capacities)
    for j, state in enumerate(observation.status):
        if state not in (UNSTARTED, PAUSED):
            continue
        duration, demands = nominal_activity(observation, j)
        if latest[j] - duration <= t + horizon:
            for k, r in enumerate(demands):
                if r and capacities[k]:
                    backlog[k] += r * duration / capacities[k]
    best = max(range(len(backlog)), key=lambda k: (backlog[k], -k), default=None)
    if best is None or backlog[best] <= 0:
        return None
    return best
