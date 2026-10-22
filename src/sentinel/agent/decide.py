"""Sentinel's decision rule (spec section 6), the needs of NOOP (spec section 5) and the record
of every decision.

Lexicographic rule: a* = lexmax (min(p, theta_D), -T, -o, -Delta, -l), with the scope loss of
DESCOPE candidates right after T. Among the candidates racing kept, the best set is filtered
component by component: every candidate tied with the best of the current set stays, ties
being material (`SentinelParams.ties`: within `se_factor` paired standard errors or below the
component's threshold); the remaining ties go to the candidate order. The component that
removed the last competitor decided, and that competitor is the runner-up. The scalarised
ablation maximises U_a = p_a - lambda_B o_a - lambda_Delta Delta_a, then prefers the lower
level and the earlier candidate. A `DecisionRecord` keeps what an explanation (WP6) or the
dashboard (WP8) needs: the epoch, the needs, every candidate with its statistics and where it
left the best set, the choice, the runner-up, the reason and what the permission gate did.
"""

import math
from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.agent.candidates import Candidate
from sentinel.agent.evaluate import CandidateStats, Evaluator, Paired
from sentinel.agent.params import COMPONENTS, Component, SentinelParams
from sentinel.policies.base import Decision

# Why a decision was taken: no deliberation (only idle workers' events, or an escalated action
# awaiting approval), an approved action applied, the needs gate, a single valid candidate,
# racing (every other candidate dropped in stage 1), the rule component that removed the
# runner-up from the best set, the candidate order, or the scalarised utility.
Reason = Literal[
    "idle_events",
    "awaiting_approval",
    "approved",
    "needs_met",
    "only_candidate",
    "racing",
    "on_time",
    "tardiness",
    "scope",
    "budget",
    "stability",
    "level",
    "order",
    "utility",
]
# What the permission gate did with the chosen action (spec section 4).
Gate = Literal["auto", "deferred", "escalated"]
PairedSE = Callable[[Paired, int, int], float]  # (component, a, b) -> paired standard error


class Choice(BaseModel):
    """The chosen candidate (index into the statistics), the reason, the runner-up (None if no
    other candidate competed) and, per candidate, the component where it left the best set
    ("racing" if dropped in stage 1, None if it was in the final set)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: NonNegativeInt
    reason: Reason
    runner_up: NonNegativeInt | None
    eliminated: tuple[str | None, ...]

    @property
    def ties(self) -> tuple[int, ...]:
        """The final best set: the candidates no component separated."""
        return tuple(a for a, out in enumerate(self.eliminated) if out is None)


def choose(stats: Sequence[CandidateStats], params: SentinelParams, paired: PairedSE) -> Choice:
    """The candidate of the decision rule of `params` (spec section 6) among those not dropped;
    `paired` gives the paired standard error of a stochastic component between two candidates
    on their common rollouts."""
    survivors = [a for a, s in enumerate(stats) if not s.dropped]
    if not survivors:
        raise ValueError("no candidate to choose from")
    eliminated: list[str | None] = ["racing" if s.dropped else None for s in stats]
    if params.rule == "scalarised":
        ranked = sorted(survivors, key=lambda a: (-stats[a].utility, stats[a].level, a))
        for a in ranked[1:]:
            eliminated[a] = "utility"
        runner = ranked[1] if len(ranked) > 1 else _best_dropped(stats)
        return Choice(
            index=ranked[0], reason="utility", runner_up=runner, eliminated=tuple(eliminated)
        )
    current = survivors
    stage: dict[int, int] = {}  # candidate -> position in COMPONENTS where it left
    for position, component in enumerate(COMPONENTS):
        if len(current) == 1:
            break
        best = min(current, key=lambda a: (_value(stats[a], component), a))
        kept = []
        for a in current:
            worse = _value(stats[a], component) - _value(stats[best], component)
            if a == best or params.ties(component, worse, _se(paired, component, best, a)):
                kept.append(a)
            else:
                eliminated[a] = component
                stage[a] = position
        current = kept
    index = current[0]  # survivors are in candidate order, and filtering keeps it
    if len(current) > 1:
        return Choice(
            index=index, reason="order", runner_up=current[1], eliminated=tuple(eliminated)
        )
    if not stage:
        runner = _best_dropped(stats)
        reason: Reason = "racing" if runner is not None else "only_candidate"
        return Choice(index=index, reason=reason, runner_up=runner, eliminated=tuple(eliminated))
    last = max(stage.values())
    component = COMPONENTS[last]
    runner = min(
        (a for a, p in stage.items() if p == last),
        key=lambda a: (_value(stats[a], component), a),
    )
    return Choice(index=index, reason=component, runner_up=runner, eliminated=tuple(eliminated))


def _se(paired: PairedSE, component: Component, a: int, b: int) -> float:
    """The paired standard error of a stochastic component; 0 for the deterministic ones."""
    match component:
        case "on_time" | "tardiness" | "budget":
            return paired(component, a, b)
    return 0.0


def _value(s: CandidateStats, component: Component) -> float:
    """The candidate's value of a rule component, smaller is better."""
    match component:
        case "on_time":
            return -s.capped
        case "tardiness":
            return s.tardiness
        case "scope":
            return s.scope_loss
        case "budget":
            return s.overrun
        case "stability":
            return s.deviation
        case "level":
            return s.level


def _best_dropped(stats: Sequence[CandidateStats]) -> int | None:
    """The best candidate racing dropped (capped on-time estimate, tardiness, order)."""
    dropped = [a for a, s in enumerate(stats) if s.dropped]
    return min(dropped, key=lambda a: (-stats[a].capped, stats[a].tardiness, a), default=None)


class Needs(BaseModel):
    """The needs of NOOP (spec section 5): n_D = max(0, theta_D - p_NOOP) and n_B = o_NOOP
    from `rollouts` rollouts, and whether both are within epsilon_D and epsilon_B."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deadline: NonNegativeFloat
    budget: NonNegativeFloat
    p_on_time: NonNegativeFloat
    rollouts: NonNegativeInt
    met: bool


def assess_needs(
    evaluator: Evaluator,
    base: Candidate,
    *,
    stage1: int | None = None,
    rollouts: int | None = None,
) -> Needs:
    """The needs of NOOP (spec section 5) from N_1 rollouts, or from N where the N_1 ones do
    not show a need beyond `se_factor` standard errors (deadline: theta_D - p - epsilon_D;
    budget: the overrun of the mean cost lowered by that many errors, minus epsilon_B). The gate
    is met only on N rollouts. `stage1` and `rollouts` replace N_1 and N of the parameters."""
    params = evaluator.params
    n1 = params.n_stage1 if stage1 is None else stage1
    n = params.n_rollouts if rollouts is None else rollouts
    k = params.se_factor
    outcomes = evaluator.extend(base, n1)
    on_time = [float(x) for x in outcomes.on_time[:n1]]
    p, se_p = _mean_se(on_time)
    cost, se_cost = _mean_se(outcomes.cost[:n1])
    clear = params.theta_d - p - params.eps_d > k * se_p
    clear = clear or evaluator.overrun(cost - k * se_cost) > params.eps_b
    used = n1
    if not clear:
        outcomes = evaluator.extend(base, n)
        used = n
        p, _ = _mean_se([float(x) for x in outcomes.on_time[:n]])
        cost, _ = _mean_se(outcomes.cost[:n])
    deadline = max(0.0, params.theta_d - p)
    budget = evaluator.overrun(cost)
    return Needs(
        deadline=deadline,
        budget=budget,
        p_on_time=p,
        rollouts=used,
        met=deadline <= params.eps_d and budget <= params.eps_b,
    )


def _mean_se(values: Sequence[float]) -> tuple[float, float]:
    """Mean and its standard error (sample standard deviation / sqrt n; 0 for n < 2)."""
    n = len(values)
    mean = math.fsum(values) / n
    if n < 2:
        return mean, 0.0
    variance = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance / n)


class CandidateRecord(CandidateStats):
    """A candidate's statistics with its operations and where it left the best set."""

    decision: Decision
    eliminated: str | None = None


class DecisionRecord(BaseModel):
    """One decision of Sentinel: the `day`, whether it deliberated, the NOOP `needs`, every
    candidate with its statistics (in candidate order), the `chosen` label, the `runner_up`, the
    `reason` (the deciding component), the candidates `tied` in the final best set, what the
    permission `gate` did with the choice and, for an escalation, its `approval_day`; `decision`
    is what was applied (NOOP when deferred or escalated). `discarded` names an approved action
    that was no longer valid on its approval day and gave way to this deliberation. Also the
    rule, the rollouts and CP-SAT searches run, and the wall time of generating, evaluating and
    deciding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    deliberated: bool
    rule: Literal["lexicographic", "scalarised"]
    reason: Reason
    chosen: str
    decision: Decision
    runner_up: str | None = None
    gate: Gate | None = None
    approval_day: NonNegativeInt | None = None
    discarded: str | None = None
    needs: Needs | None = None
    candidates: tuple[CandidateRecord, ...] = ()
    tied: tuple[str, ...] = ()
    rollouts: NonNegativeInt = 0
    cp_solves: NonNegativeInt = 0
    cp_fallbacks: NonNegativeInt = 0
    generation_s: NonNegativeFloat = 0.0
    evaluation_s: NonNegativeFloat = 0.0
    wall_time_s: NonNegativeFloat = 0.0
