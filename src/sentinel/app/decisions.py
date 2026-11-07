"""The decision model of the v2 interface (spec section 11.8; docs/design/v2-spec.md, section 3):
the validity date and cost of delay of a pending recommendation, its corrections, and the brief
stored with a decision. Pure functions of a live project; the services store their results as
events of the project's log."""

import math
from dataclasses import dataclass
from typing import Literal

from sentinel.agent.candidates import Candidate, noop, optional_values
from sentinel.agent.decide import CandidateRecord
from sentinel.agent.evaluate import Evaluator, instability
from sentinel.app.events import Brief
from sentinel.app.live import LiveProject
from sentinel.app.planning import (
    FORECAST_ROLLOUTS,
    ApprovalEvaluator,
    Impact,
    Recommendation,
    candidate_of,
    makespan_quantiles,
    sentinel_params,
)
from sentinel.app.views import person_names
from sentinel.experiments.runs import derive_seed
from sentinel.policies.base import Decision, Descope, Operation, Overtime, Reseq, Shift, Subst
from sentinel.simulation.engine import rehearse
from sentinel.simulation.state import (
    PAUSED,
    RUNNING,
    UNSTARTED,
    Observation,
    overtime_cap,
    successor_lists,
    worker_roles,
)

GATE = 0  # the v2 interface's autonomy: every action other than NOOP is approved (11.8)
VALIDITY_DAYS = 10  # at most this many days of waiting are evaluated (section 3)
WINDOWS = (5, 10, 15, 20)  # the OVERTIME windows a correction offers, in working days
Parameter = Literal["subst", "overtime", "descope", "none"]


# --------------------------------------------------------------------------- validity


@dataclass(frozen=True)
class ValidityResult:
    """p(delta) for delta = 0, 1, ... (as evaluated), NOOP's chance, the last day the action
    still helps (None if it never gained epsilon_D) and the chance lost per day of waiting."""

    chances: tuple[float, ...]
    noop: float
    valid_day: int | None
    delay: float | None


def validity(project: LiveProject, recommendation: Recommendation) -> ValidityResult:
    """The validity date and cost of delay of the recommended action (spec section 11.8): the
    action approved delta days later in each of the forecast's worlds (the rollouts of section 6
    with delta_h = delta), delta = 0, 1, ... until it gains less than epsilon_D over NOOP or
    delta = 10."""
    chosen = recommendation.chosen
    observation = project.observation()
    if chosen is None or observation.day != recommendation.day:
        raise ValueError("the recommendation is not the one of the current observation")
    base = sentinel_params(project, GATE)
    seed = derive_seed(project.definition.settings.seed, "forecast", str(observation.day))
    candidate = candidate_of(chosen, observation)
    first = Evaluator(observation, seed, base.model_copy(update={"approval_delay": 0}))
    p_noop = first.stats(noop(observation), FORECAST_ROLLOUTS, 0.0).p_on_time
    chances: list[float] = []
    valid: int | None = None
    for delta in range(VALIDITY_DAYS + 1):
        evaluator = (
            first
            if delta == 0
            else Evaluator(observation, seed, base.model_copy(update={"approval_delay": delta}))
        )
        p = evaluator.stats(candidate, FORECAST_ROLLOUTS, 0.0).p_on_time
        chances.append(p)
        if p - p_noop < base.eps_d - 1e-12:
            break
        valid = observation.day + delta
    delay = None
    if valid is not None and len(chances) > 1:
        delay = max(0.0, (chances[0] - chances[-1]) / (len(chances) - 1))
    return ValidityResult(tuple(chances), p_noop, valid, delay)


# --------------------------------------------------------------------------- corrections


@dataclass(frozen=True)
class Option:
    """A correction: its key (stable in a form), the operation it puts in place of the one
    corrected, and what it names: a person, a role with number and days, or a task."""

    key: str
    operation: Operation
    person: str | None = None
    role: str | None = None
    workers: int = 0
    days: int = 0
    task: str | None = None
    current: bool = False


def corrected_index(decision: Decision) -> int | None:
    """The operation a correction changes: the first one that is not a plan part."""
    return next(
        (i for i, op in enumerate(decision.operations) if not isinstance(op, Reseq | Shift)),
        None,
    )


def parameter_of(decision: Decision) -> Parameter:
    index = corrected_index(decision)
    if index is None:
        return "none"
    op = decision.operations[index]
    return (
        "subst"
        if isinstance(op, Subst)
        else "overtime"
        if isinstance(op, Overtime)
        else ("descope" if isinstance(op, Descope) else "none")
    )


def options(project: LiveProject, recommendation: Recommendation) -> list[Option]:
    """The corrections of the recommended action the engine accepts (spec section 11.8), the
    current one first; empty for SHIFT and RESEQ alone."""
    chosen = recommendation.chosen
    if chosen is None:
        return []
    observation = project.observation()
    decision = chosen.decision
    index = corrected_index(decision)
    if index is None:
        return []
    op = decision.operations[index]
    found: list[Option] = []
    workers = project.worker_keys()
    names = person_names(project)
    model = project.require_model()
    keys = {j: key for key, j in project.activity_ids().items()}
    nodes = project.nodes()
    if isinstance(op, Subst):
        roles = worker_roles(observation)
        busy = {
            w
            for j, state in enumerate(observation.status)
            if state in (RUNNING, PAUSED)
            for w in observation.assigned[j]
        }
        first, rest = op.workers[0], op.workers[1:]
        for w, here in enumerate(observation.present):
            if not here or roles[w] != roles[first] or (w in busy and w != first) or w in rest:
                continue
            name = names.get(workers[w], workers[w]) if w < len(workers) else str(w)
            new = Subst(activity=op.activity, workers=(w, *rest))
            found.append(Option(f"subst-{w}", new, person=name, current=w == first))
    elif isinstance(op, Overtime):
        for k, name in enumerate(model.role_names):
            capacity = observation.instance.roles[k].capacity
            cap = overtime_cap(capacity, floor=observation.overtime_floor)
            for u in range(1, cap + 1):
                for days in sorted({*WINDOWS, op.days}):
                    hire = Overtime(role=k, workers=u, days=days)
                    current = hire == op
                    key = f"ot-{k}-{u}-{days}"
                    found.append(
                        Option(key, hire, role=name, workers=u, days=days, current=current)
                    )
    elif isinstance(op, Descope):
        values = optional_values(observation)
        sink = observation.instance.sink_id
        successors = successor_lists(observation)
        for j in sorted(values):
            if observation.status[j] != UNSTARTED or successors[j] != [sink] or j not in keys:
                continue
            task = nodes[keys[j]].name
            found.append(
                Option(f"descope-{j}", Descope(activity=j), task=task, current=j == op.activity)
            )
    valid = [o for o in found if o.current or _accepted(observation, decision, index, o)]
    valid.sort(key=lambda o: not o.current)
    return valid


def replaced(decision: Decision, index: int, operation: Operation) -> Decision:
    ops = list(decision.operations)
    ops[index] = operation
    return Decision(operations=tuple(ops))


def _accepted(observation: Observation, decision: Decision, index: int, option: Option) -> bool:
    """Whether the engine accepts the corrected non-plan operations on today's state."""
    ops = tuple(
        op
        for op in replaced(decision, index, option.operation).operations
        if not isinstance(op, Reseq | Shift)
    )
    return not rehearse(observation, Decision(operations=ops))[1]


def correct(project: LiveProject, recommendation: Recommendation, key: str) -> Recommendation:
    """The recommendation with the corrected action as its choice (spec section 11.8): evaluated
    as a row of the comparison (applied at once on the forecast's worlds, as approving it
    applies it), the action first recommended kept as an alternative and the runner-up."""
    chosen = recommendation.chosen
    comparison = recommendation.comparison
    if chosen is None or comparison is None:
        raise ValueError("nothing to correct")
    option = next((o for o in options(project, recommendation) if o.key == key), None)
    if option is None:
        raise ValueError(f"no correction {key!r}")
    index = corrected_index(chosen.decision)
    assert index is not None
    observation = project.observation()
    decision = replaced(chosen.decision, index, option.operation)
    params = sentinel_params(project, GATE)
    label = f"{chosen.label.split('~')[0]}~{key}"
    substituted = sum(len(op.workers) for op in decision.operations if isinstance(op, Subst))
    candidate = Candidate(
        label=label,
        kind=chosen.kind,
        decision=decision,
        plan=observation.plan,
        substituted=substituted,
        scope_loss=chosen.scope_loss,
    )
    seed = derive_seed(project.definition.settings.seed, "forecast", str(observation.day))
    evaluator = ApprovalEvaluator(project, observation, seed, params)
    deviation = instability(observation, candidate, params.kappa_h)
    stats = evaluator.stats(candidate, FORECAST_ROLLOUTS, deviation)
    record = CandidateRecord(**stats.model_dump(), decision=decision)
    outcomes = evaluator.outcomes[label]
    n = FORECAST_ROLLOUTS
    impact = Impact(
        label=label,
        kind=chosen.kind,
        p_on_time=stats.p_on_time,
        tardiness=stats.tardiness,
        mean_cost=stats.mean_cost,
        overrun=stats.overrun,
        rollouts=n,
        mean_makespan=math.fsum(outcomes.makespan[:n]) / n,
        quantiles=makespan_quantiles(outcomes.makespan[:n]),
    )
    old = recommendation.record
    candidates = (
        *(c for c in old.candidates if c.label != label),
        record,
    )
    first, *others = comparison.impacts
    impacts = (impact, *(i for i in (first, *others) if i.label != label))
    new_record = old.model_copy(
        update={
            "chosen": label,
            "decision": decision,
            "runner_up": first.label if first.label != label else old.runner_up,
            "candidates": candidates,
        }
    )
    return recommendation.model_copy(
        update={
            "record": new_record,
            "comparison": comparison.model_copy(update={"impacts": impacts}),
            "changes": (),
        }
    )


def brief_of(
    recommendation: Recommendation, valid_day: int | None, delay: float | None
) -> Brief | None:
    """The brief stored with a decision (spec section 11.8), None without the comparison."""
    chosen = recommendation.impact(recommendation.record.chosen)
    without = recommendation.impact("NOOP")
    if chosen is None or without is None:
        return None
    return Brief(
        p_before=without.p_on_time,
        p_after=chosen.p_on_time,
        finish_before=None if without.quantiles is None else without.quantiles[1],
        finish_after=None if chosen.quantiles is None else chosen.quantiles[1],
        cost_before=without.mean_cost,
        cost_after=chosen.mean_cost,
        valid_day=valid_day,
        delay=delay,
    )


def distribution(
    project: LiveProject, recommendation: Recommendation
) -> tuple[list[int], list[int]]:
    """The makespans of the forecast's worlds with the recommended action applied at once and
    without it (the rows of the comparison, spec section 11.5 item 3), for the details."""
    chosen = recommendation.chosen
    observation = project.observation()
    if chosen is None or observation.day != recommendation.day:
        raise ValueError("the recommendation is not the one of the current observation")
    params = sentinel_params(project, GATE)
    seed = derive_seed(project.definition.settings.seed, "forecast", str(observation.day))
    evaluator = ApprovalEvaluator(project, observation, seed, params)
    n = FORECAST_ROLLOUTS
    with_action = evaluator.extend(candidate_of(chosen, observation), n).makespan[:n]
    without = evaluator.extend(noop(observation), n).makespan[:n]
    return list(with_action), list(without)
