"""Spec v1.8 and v1.8.1: the material rule on a hopeless epoch, the permission gate in the world
and in rollouts with approved actions planned again on their approval day, DESCOPE and its
optional activities, and B, c_k and c_OT_k in the observation (spec sections 3-6)."""

from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pytest

from sentinel.agent.candidates import Candidate, approve, generate, noop
from sentinel.agent.decide import choose
from sentinel.agent.evaluate import Evaluator, race
from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.experiments.policy_runs import scope_loss
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import Decision, Descope, Overtime, Reseq, Shift, Subst
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.sentinel import Sentinel
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.residual import planning_view
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import Descoped, SimulationResult, rehearse, simulate
from sentinel.simulation.events import AbsenceDraw, DisruptionParams, ScenarioStreams
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.state import RUNNING, Observation, successor_lists
from sentinel.simulation.uncertainty import PertParams, derive_budget, optional_activities

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)  # X = 1, so P_j = p_j
NONE = DisruptionParams.none()
LIVELY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.02, lambda_n=0.05)
SMALL = SentinelParams(n_rollouts=16, n_stage1=8)


class Script:
    """A policy that returns a fixed decision on given days."""

    def __init__(self, decisions: dict[int, Decision]) -> None:
        self.decisions = decisions

    def decide(self, observation: Observation) -> Decision:
        return self.decisions.get(observation.day, Decision())


def assert_feasible(instance: ProjectInstance, result: SimulationResult) -> None:
    realised, schedule = realised_instance(instance, result)  # validates acyclicity
    assert validate_schedule(realised, schedule) == []
    assert execution_violations(instance, result) == []


def random_instance(build: Builder, seed: int, n: int = 12) -> ProjectInstance:
    """n real activities on two roles of five and ten workers (as in test_sentinel)."""
    rng = np.random.default_rng(seed)
    capacities = (5, 10)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(1, 7, size=n).tolist(), 0]
    demands = [[0, 0], *([int(rng.integers(0, c // 2 + 1)) for c in capacities] for _ in range(n))]
    return build(
        durations, [*demands, [0, 0]], [sorted(s) for s in successors], capacities=capacities
    )


def absence_case(build: Builder, monkeypatch: pytest.MonkeyPatch, deadline: int) -> Observation:
    """Role 0 has workers 0 and 1, role 1 worker 2. A (p 6, worker 0) and B (p 2, worker 1)
    start on day 0; C (p 1, role 1) follows B on day 2. Worker 0 is out from day 1, announced
    for one day, so on day 2 A is paused with 5 days of work left and worker 1 is idle; the
    posterior of the absence (E[L] = 3) has the worker back on day 3 or later."""
    inst = build(
        [0, 6, 2, 1, 0],
        [[0, 0], [1, 0], [1, 0], [0, 1], [0, 0]],
        [[1, 2], [4], [3], [4], []],
        capacities=(2, 1),
    )
    onsets = {1: [AbsenceDraw(worker=0, length=6, announced=1)]}

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    monkeypatch.setattr(engine, "ScenarioStreams", Forced)
    quiet = DisruptionParams(lambda_a=0.0, mean_absence=3, lambda_s=0.0, lambda_n=0.0)
    plan = Schedule(starts=(0, 0, 0, 2, 6))
    result = simulate(
        inst, plan, NoReaction(), 0, pert=EXACT, disruptions=quiet, deadline=deadline,
        observe_days=[2],
    )  # fmt: skip
    return result.observations[0]


def subst_candidate(observation: Observation) -> Candidate:
    decision = Decision(operations=(Subst(activity=1, workers=(1,)),))
    after = rehearse(observation, decision)[0]
    return Candidate(
        label="SUBST(1)", kind="subst", decision=decision, plan=after.plan, substituted=1
    )


def test_observations_carry_the_budget_and_the_costs(build: Builder) -> None:
    inst = build([0, 2, 3, 0], [[0, 0], [1, 1], [2, 0], [0, 0]], [[1, 2], [3], [3], []], (2, 2))
    plan = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
    costs = (1.0, 2.0)
    result = simulate(
        inst, plan, NoReaction(), 1, pert=PertParams(), disruptions=NONE, deadline=9,
        costs=costs, observe_days=[0],
    )  # fmt: skip
    seen = result.observations[0]
    assert seen.costs == costs and seen.overtime_costs == (1.5, 3.0)
    assert seen.budget == pytest.approx(derive_budget(inst, costs=costs, params=PertParams()))
    assert Observation.model_validate_json(seen.model_dump_json()) == seen
    assert Evaluator(seen, 0, SMALL).budget == seen.budget
    again = simulate(
        inst, plan, NoReaction(), 1, pert=PertParams(), disruptions=NONE, deadline=9,
        observe_days=[0], budget=123.0,
    )  # fmt: skip
    assert again.observations[0].budget == 123.0


def test_a_hopeless_epoch_chooses_the_lowest_tardiness(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With D = 5 every candidate is late in every rollout. Substituting A's absent member ends
    A on day 8 (T = 3); waiting ends it on day 3 + L >= 8. The on-time component ties at 0, and
    the material, significant tardiness difference decides, in racing and in a deliberation."""
    observation = absence_case(build, monkeypatch, deadline=5)
    params = SentinelParams(n_rollouts=40, n_stage1=10, autonomy=3)
    candidates = [noop(observation), subst_candidate(observation)]
    evaluation = race(Evaluator(observation, 3, params), candidates)
    assert [s.p_on_time for s in evaluation.stats] == [0.0, 0.0]
    assert not any(s.dropped for s in evaluation.stats)  # nothing is worse in min(p, theta_D)
    assert evaluation.stats[1].tardiness == 3.0 < evaluation.stats[0].tardiness - 0.5
    choice = choose(evaluation.stats, params, evaluation.paired)
    assert (choice.index, choice.reason, choice.runner_up) == (1, "tardiness", 0)
    record = Sentinel(params, seed=3).deliberate(observation)
    assert record.chosen == "SUBST(1)" and record.reason == "tardiness"
    assert record.gate == "auto" and record.decision == candidates[1].decision


def test_rollouts_imagine_the_approval_delay(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D = 8. Substituting at once ends A on day 8 in every rollout. Approved a day later, the
    substitution applies on day 3 only where the member is still absent (then A ends on day 9),
    and where the member is back on day 3 it is invalid and A ends on day 8 without it: the
    on-time estimate is NOOP's, the tardiness below NOOP's and above the immediate one's."""
    observation = absence_case(build, monkeypatch, deadline=8)
    subst = subst_candidate(observation)
    at_once = Evaluator(observation, 5, SentinelParams(autonomy=3))
    delayed = Evaluator(observation, 5, SentinelParams(autonomy=2))  # SUBST has level 2
    n = 40
    now, later, waiting = at_once.stats(subst, n, 0.0), delayed.stats(subst, n, 0.0), None
    waiting = delayed.stats(noop(observation), n, 0.0)
    assert (now.delay, later.delay) == (0, 1)
    assert now.p_on_time == 1.0 and now.tardiness == 0.0
    assert later.p_on_time == waiting.p_on_time < 1.0
    assert 0.0 < later.tardiness < waiting.tardiness


class Watching(Sentinel):
    """Sentinel that keeps every observation it decides on."""

    def __init__(self, params: SentinelParams, seed: int) -> None:
        super().__init__(params, seed=seed)
        self.seen: list[Observation] = []

    def decide(self, observation: Observation) -> Decision:
        self.seen.append(observation)
        return super().decide(observation)


def long_absence(
    build: Builder,
    monkeypatch: pytest.MonkeyPatch,
    autonomy: int,
    deadline: int,
    *,
    relapse: bool = False,
) -> tuple[SimulationResult, Sentinel]:
    """The instance of `absence_case`, but worker 0 is out on days 1-6, announced so; Sentinel
    deliberates every day (T_r = 1). From day 2 substituting is the only remedy: at once A ends
    on day 8, after a day's approval on day 9, waiting on day 12. With `relapse`, worker 1, the
    only possible substitute, is out on days 3-4, announced so."""
    inst = build(
        [0, 6, 2, 1, 0],
        [[0, 0], [1, 0], [1, 0], [0, 1], [0, 0]],
        [[1, 2], [4], [3], [4], []],
        capacities=(2, 1),
    )
    onsets = {1: [AbsenceDraw(worker=0, length=6, announced=6)]}
    if relapse:
        onsets[3] = [AbsenceDraw(worker=1, length=2, announced=2)]

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    monkeypatch.setattr(engine, "ScenarioStreams", Forced)
    quiet = DisruptionParams(lambda_a=0.0, mean_absence=3, lambda_s=0.0, lambda_n=0.0)
    params = SentinelParams(n_rollouts=16, n_stage1=8, autonomy=autonomy, review_period=1)
    policy = Sentinel(params, seed=4)
    result = simulate(
        inst, Schedule(starts=(0, 0, 0, 2, 6)), policy, 0, pert=EXACT, disruptions=quiet,
        deadline=deadline, review_period=1, debug=True,
    )  # fmt: skip
    assert_feasible(inst, result)
    return result, policy


def test_full_autonomy_escalates_nothing_and_zero_autonomy_gates_every_action(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lambda = 3 substitutes on day 2 at once. Lambda = 0 gates every action: with D = 8 the
    urgency (tau = LS_A - t = 0) escalates the substitution, approved and applied on day 3;
    with D = 12 (tau = 4 > tau_def = 3) it is first deferred, escalated on day 3 and applied on
    day 4. Every applied action comes from an approval."""
    free, policy = long_absence(build, monkeypatch, autonomy=3, deadline=8)
    stats = policy.stats
    assert stats.escalations == stats.deferrals == stats.approvals_applied == 0
    assert {r.gate for r in policy.records} <= {None, "auto"}
    assert [(s.day, s.activity) for s in free.substitutions] == [(2, 1)] and free.makespan == 8
    for deadline, applied, expected in ((8, 3, ["escalated"]), (12, 4, ["deferred", "escalated"])):
        gated, policy = long_absence(build, monkeypatch, autonomy=0, deadline=deadline)
        records = policy.records
        days = {r.day for r in records}
        for record in records:
            if record.deliberated and record.chosen != "NOOP":
                assert record.gate in ("deferred", "escalated") and record.decision == Decision()
            if record.gate == "escalated":  # the approval day was a decision epoch
                assert record.approval_day == record.day + 1 and record.approval_day in days
            if record.decision.operations:
                assert record.reason == "approved"
        gates = [r.gate for r in records if r.gate is not None]
        assert gates == expected and policy.stats.approvals_applied == 1
        assert [(s.day, s.activity) for s in gated.substitutions] == [(applied, 1)]
        assert gated.makespan == applied + 6


def test_an_approved_subst_whose_worker_became_absent_is_discarded_and_redeliberated(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lambda = 0, D = 8: SUBST(1) by worker 1 is escalated on day 2, but worker 1 falls ill on
    day 3, its approval day. The substitution is invalid there, so it is discarded and Sentinel
    deliberates afresh, now without a substitute to propose; nobody is substituted that day."""
    result, policy = long_absence(build, monkeypatch, autonomy=0, deadline=8, relapse=True)
    escalation = policy.records[[r.day for r in policy.records].index(2)]
    assert (escalation.chosen, escalation.gate, escalation.approval_day) == (
        "SUBST(1)",
        "escalated",
        3,
    )
    record = policy.records[[r.day for r in policy.records].index(3)]
    assert record.discarded == "SUBST(1)" and record.deliberated and record.reason != "approved"
    assert all(c.kind != "subst" for c in record.candidates)
    assert policy.stats.approvals_discarded == 1
    assert all(s.day != 3 for s in result.substitutions)


def stale_case(build: Builder) -> tuple[ProjectInstance, Schedule]:
    """Roles X, Y and Z of one worker each. D (1; p 2, Z) starts on day 0, A (2; p 4, X) is
    planned for day 1, B (3; p 1, X) for day 5 and its successor C (4; p 4, Y) for day 6: the
    plan ends on day 10, SHIFT (A first) on day 9, B before A on day 5."""
    inst = build(
        [0, 2, 4, 1, 4, 0],
        [[0, 0, 0], [0, 0, 1], [1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]],
        [[1, 2, 3], [5], [5], [4], [5], []],
        capacities=(1, 1, 1),
    )
    return inst, Schedule(starts=(0, 0, 1, 5, 6, 10))


def stale_world(build: Builder) -> tuple[ProjectInstance, SimulationResult, Watching]:
    """The stale case with D = 7 under Sentinel with Lambda = 1 (RESEQ needs approval)."""
    inst, plan = stale_case(build)
    policy = Watching(SentinelParams(n_rollouts=8, n_stage1=4, autonomy=1), seed=3)
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, deadline=7, debug=True
    )  # fmt: skip
    assert_feasible(inst, result)
    return inst, result, policy


def test_an_approved_reseq_with_a_stale_plan_is_replanned_and_applied(build: Builder) -> None:
    """Only RESEQ-M can meet D = 7, and its urgency (LS_B - t = 2) escalates it on day 0. Its
    plan lists D, which starts on day 0, so the engine would reject it on the approval day 1.
    The human approves the intent: RESEQ-M planned again on the day-1 view (B on day 1, then A
    and C on day 2) is applied, and the project ends on day 6."""
    _, result, policy = stale_world(build)
    first, approval = policy.records[0], policy.records[1]
    assert (first.day, first.chosen, first.gate, first.approval_day) == (
        0,
        "RESEQ-M",
        "escalated",
        1,
    )
    escalated = next(c.decision for c in first.candidates if c.label == "RESEQ-M")
    seen = policy.seen[1]
    assert seen.day == 1 and seen.status[1] == RUNNING
    assert rehearse(seen, escalated)[1] != ()  # the plan of day 0 is stale on day 1
    assert (approval.day, approval.reason, approval.chosen) == (1, "approved", "RESEQ-M")
    assert approval.decision == Decision(operations=(Reseq(starts={2: 2, 3: 1, 4: 2, 5: 6}),))
    assert rehearse(seen, approval.decision)[1] == ()
    stats = policy.stats
    assert (stats.escalations, stats.approvals_applied, stats.approvals_discarded) == (1, 1, 0)
    assert result.makespan == 6 and result.reseqs == 1


def test_a_rollout_imagines_the_approval_the_world_applies(build: Builder) -> None:
    """On the stale case every sampled world is the true one (exact durations, no disruptions),
    so a rollout of the escalated RESEQ-M from the day-0 observation approves on day 1 the same
    re-planned action as the world and ends with the same starts, finishes and cost."""
    _, result, policy = stale_world(build)
    observation = policy.seen[0]
    params = policy.params
    candidate = next(
        c for c in generate(observation, params=params).candidates if c.label == "RESEQ-M"
    )
    evaluator = Evaluator(observation, 9, params)
    state, applied = evaluator.play(candidate, 0)
    assert applied == policy.records[1].decision
    assert tuple(state.start) == result.starts and tuple(state.finish) == result.finishes
    assert state.cost == result.total_cost and state.start[state.sink] == 6
    again = evaluator.play(candidate, 1)[1]  # the next rollout reuses the plan part
    assert again == applied and (evaluator.replan_solves, evaluator.replans_reused) == (1, 1)


def test_an_approved_overtime_replans_with_the_temporary_workers(build: Builder) -> None:
    """Role 0 has five workers (one temporary worker at most). A (3 workers, p 3) runs from day
    0 and B (3 workers, p 3) is planned after it, on day 3. OT(0) + RESEQ-M escalated on day 0 is
    stale on day 1 (its plan lists A); approved there, the hire is re-validated and RESEQ-M
    planned with the temporary worker starts B on day 1, which the plan alone could not."""
    inst = build([0, 3, 3, 0], [[0], [3], [3], [0]], [[1, 2], [3], [3], []], capacities=(5,))
    seen = simulate(
        inst, Schedule(starts=(0, 0, 3, 6)), NoReaction(), 0, pert=EXACT, disruptions=NONE,
        deadline=4, observe_days=[0, 1],
    ).observations  # fmt: skip
    candidate = next(
        c for c in generate(seen[0], params=SMALL).candidates if c.kind == "ot_reseq_m"
    )
    assert rehearse(seen[1], candidate.decision)[1] != ()
    approval = approve(seen[1], candidate, SMALL)
    hire, plan = approval.decision.operations
    assert approval.rejection is None and hire == Overtime(role=0, workers=1, days=10)
    assert isinstance(plan, Reseq) and plan.starts == {2: 1, 3: 4}
    assert rehearse(seen[1], Decision(operations=(plan,)))[1] != ()  # infeasible without the hire


def test_approval_on_the_epoch_day_rebuilds_every_candidate(build: Builder) -> None:
    """Approval and candidate generation share `prepare`: approving a candidate on the day it
    was generated gives back its decision, every kind of plan part planned again."""
    kinds = set()
    for seed in (40, 41):
        inst = random_instance(build, seed)
        plan = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
        seen = simulate(
            inst, plan, NoReaction(), seed, pert=PertParams(), disruptions=LIVELY,
            deadline=plan.makespan(inst), observe_days=range(0, 30, 5),
        ).observations  # fmt: skip
        for observation in seen:
            for candidate in generate(observation, params=SMALL).candidates:
                kinds.add(candidate.kind)
                approval = approve(observation, candidate, SMALL)
                assert approval.rejection is None and approval.decision == candidate.decision
    assert {"shift", "reseq_m", "reseq_s", "subst", "subst_all_reseq_m", "ot_reseq_m"} <= kinds


def test_descope_removes_only_unstarted_optional_activities(build: Builder) -> None:
    """1 (p 2) precedes 2 (p 2); 3 (p 3) and 4 (p 2) are parallel; 2, 3 and 4 precede the sink
    5; O = {2, 4}. On day 0 DESCOPE(1) and DESCOPE(3) are rejected (not optional) and
    DESCOPE(2) applies: 1 now precedes the sink. DESCOPE(4) on day 1 is rejected (running). The
    project ends on day 3 without 2, acyclic and feasible, and the rebuilt state agrees."""
    inst = build(
        [0, 2, 2, 3, 2, 0],
        [[0], [1], [1], [1], [1], [0]],
        [[1, 3, 4], [2], [5], [5], [5], []],
        capacities=(3,),
    )
    plan = Schedule(starts=(0, 0, 2, 0, 0, 4))
    script = Script(
        {
            0: Decision(operations=(Descope(activity=1), Descope(activity=2), Descope(activity=3))),
            1: Decision(operations=(Descope(activity=4),)),
        }
    )
    result = simulate(
        inst, plan, script, 0, pert=EXACT, disruptions=NONE, deadline=6, review_period=1,
        optional=(2, 4), observe_days=[1], debug=True,
    )  # fmt: skip
    assert result.descoped == (Descoped(day=0, activity=2, value=2.0),)
    reasons = [(r.day, r.operation.activity, r.reason.split(",")[0]) for r in result.rejected]  # type: ignore[union-attr]
    assert reasons == [
        (0, 1, "activity 1 is not optional"),
        (0, 3, "activity 3 is not optional"),
        (1, 4, "activity 4 is running"),
    ]
    assert result.starts[2] is None and result.starts[1] == 0 and result.makespan == 3
    assert_feasible(inst, result)
    assert scope_loss(result, inst, (2, 4)) == pytest.approx(0.5)
    seen = result.observations[0]
    assert seen.status[2] == "removed" and seen.optional == (2, 4)
    assert successor_lists(seen)[1] == [5] and 2 not in planning_view(seen).activities
    with pytest.raises(ValueError, match="optional activities"):
        simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, optional=(5,))


def test_sentinel_descopes_only_when_no_candidate_reaches_theta(build: Builder) -> None:
    """One worker; 1 (p 2) then 2 (p 5), both optional and before the sink. With D = 3 nothing
    reaches theta_D, so DESCOPE candidates join: DESCOPE(2), approved on day 1 (imagined so in
    the rollouts), ends the project on day 2; DESCOPE(1) would come too late (1 runs). With a
    plan that SHIFT repairs in time, no DESCOPE candidate is generated."""
    inst = build([0, 2, 5, 0], [[0], [1], [1], [0]], [[1, 2], [3], [3], []], capacities=(1,))
    params = SentinelParams(n_rollouts=8, n_stage1=4, descope=True)

    def run(plan: tuple[int, ...], deadline: int) -> tuple[SimulationResult, Sentinel]:
        policy = Sentinel(params, seed=1)
        result = simulate(
            inst, Schedule(starts=plan), policy, 1, pert=EXACT, disruptions=NONE,
            deadline=deadline, optional=(1, 2), debug=True,
        )  # fmt: skip
        return result, policy

    result, policy = run((0, 0, 2, 7), 3)
    first, approval = policy.records[0], policy.records[1]
    # The worlds are deterministic, so racing drops NOOP and the late DESCOPE(1) in stage 1.
    assert (first.chosen, first.reason, first.runner_up) == ("DESCOPE(2)", "racing", "NOOP")
    assert first.gate == "escalated" and first.approval_day == 1
    assert {c.label: c.delay for c in first.candidates if c.kind == "descope"} == {
        "DESCOPE(2)": 1,
        "DESCOPE(1)": 1,
    }
    assert approval.day == 1 and approval.reason == "approved"
    assert result.descoped == (Descoped(day=1, activity=2, value=5.0),) and result.makespan == 2
    assert scope_loss(result, inst, (1, 2)) == pytest.approx(5 / 7)
    assert_feasible(inst, result)
    repaired, policy = run((0, 1, 3, 8), 7)
    assert policy.records[0].chosen == "SHIFT" and repaired.descoped == ()
    assert all(c.kind != "descope" for r in policy.records for c in r.candidates)


TINY_LIKE = """\
************************************************************************
file with basedata            : tiny3.bas
initial value random generator: 1
************************************************************************
projects                      :  1
jobs (incl. supersource/sink ):  6
horizon                       :  20
RESOURCES
  - renewable                 :  1   R
  - nonrenewable              :  0   N
  - doubly constrained        :  0   D
************************************************************************
PROJECT INFORMATION:
pronr.  #jobs rel.date duedate tardcost  MPM-Time
    1      4      0       10        0       10
************************************************************************
PRECEDENCE RELATIONS:
jobnr.    #modes  #successors   successors
   1        1          3           2   3   4
   2        1          1           5
   3        1          1           6
   4        1          1           6
   5        1          1           6
   6        1          0
************************************************************************
REQUESTS/DURATIONS:
jobnr. mode duration  R 1
------------------------------------------------------------------------
  1      1     0       0
  2      1     3       2
  3      1     2       2
  4      1     4       1
  5      1     2       1
  6      1     0       0
************************************************************************
RESOURCEAVAILABILITIES:
  R 1
    3
************************************************************************
"""


def test_optional_activities_are_the_real_activities_before_the_sink_alone(
    tmp_path: Path, tiny: ProjectInstance
) -> None:
    """O is every real activity whose only successor is the sink (spec section 4): three of the
    four real activities of a tiny.sm-like instance (1 precedes 4), two of the three of tiny.sm."""
    path = tmp_path / "tiny3.sm"
    path.write_text(TINY_LIKE, encoding="utf-8")
    assert optional_activities(load_psplib(path)) == (2, 3, 4)
    assert optional_activities(tiny) == (2, 3)


@pytest.mark.data
def test_every_j30_and_j60_instance_has_three_optional_activities(psplib_root: Path) -> None:
    """All 480 J30 and 480 J60 instances have three real activities before the sink alone."""
    for set_name in ("j30", "j60"):
        stems = list_instances(set_name, psplib_root)
        assert len(stems) == 480
        for stem in stems:
            inst = load_psplib(instance_path(set_name, stem, psplib_root))
            found = optional_activities(inst)
            assert len(found) == 3, stem
            assert all(tuple(inst.activities[j].successors) == (inst.sink_id,) for j in found)


def test_the_gate_exempts_noop_and_always_stops_descope() -> None:
    """An action runs at once iff l(a) < Lambda and it has no DESCOPE; NOOP never waits."""
    shift = Decision(operations=(Shift(starts={}),))  # level 0
    reseq = Decision(operations=(Reseq(starts={}),))  # level 1
    subst = Decision(operations=(Subst(activity=1, workers=(2,)),))  # level 2
    descope = Decision(operations=(Descope(activity=1),))
    for autonomy in range(4):
        params = SentinelParams(autonomy=autonomy, approval_delay=2)
        assert not params.needs_approval(Decision()) and params.delay(Decision()) == 0
        assert params.needs_approval(descope) and params.delay(descope) == 2
        gated = [params.needs_approval(d) for d in (shift, reseq, subst)]
        assert gated == [autonomy <= 0, autonomy <= 1, autonomy <= 2]
