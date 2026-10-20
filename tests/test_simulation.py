"""Daily execution semantics of the simulator (spec sections 2-3, 3.1)."""

import math
from collections.abc import Callable, Sequence

import pytest

from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import Decision, Noop
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.bounds import earliest_starts
from sentinel.scheduling.cpsat import solve_cpsat
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import (
    Absence,
    AbsenceDraw,
    DisruptionParams,
    NewActivity,
    ScenarioStreams,
    WorkIncrease,
)
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.state import InsertedActivity, Observation
from sentinel.simulation.uncertainty import PertParams

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)  # X = 1, so P_j = p_j
NONE = DisruptionParams.none()
BUSY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1)


class EmptyPolicy:
    """Test-only policy: returns empty decisions like NoReaction but is a different class."""

    def decide(self, observation: Observation) -> Decision:
        return Decision()


class Recorder:
    """Test-only policy that keeps every observation and never intervenes."""

    def __init__(self) -> None:
        self.seen: list[Observation] = []

    def decide(self, observation: Observation) -> Decision:
        self.seen.append(observation)
        return Decision(operations=(Noop(),))


@pytest.fixture
def eight(build: Builder) -> ProjectInstance:
    """Two roles of capacity 2 with resource conflicts; activity 3 is a milestone."""
    return build(
        [0, 3, 2, 0, 2, 2, 4, 0],
        [[0, 0], [1, 0], [1, 1], [0, 0], [2, 1], [1, 1], [0, 1], [0, 0]],
        [[1, 2, 6], [3], [4], [5], [7], [7], [7], []],
        capacities=(2, 2),
    )


def lft_plan(instance: ProjectInstance) -> Schedule:
    return serial_sgs(instance, lft_priorities(instance), lower_is_better=True)


def forced_streams(
    onsets: dict[int, list[AbsenceDraw]] | None = None,
    shocks: dict[int, tuple[int, float]] | None = None,
) -> type[ScenarioStreams]:
    """Streams with real durations but absences and D2 shocks fixed by the test."""

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return (onsets or {}).get(day, [])

        def work_shock(self, activity: int, first: int, last: int) -> tuple[int, float] | None:
            shock = (shocks or {}).get(activity)
            return shock if shock is not None and first <= shock[0] <= last else None

    return Forced


def with_durations(instance: ProjectInstance, durations: Sequence[int]) -> ProjectInstance:
    """The instance with p_j replaced by the given durations."""
    activities = tuple(
        act.model_copy(update={"duration": p})
        for act, p in zip(instance.activities, durations, strict=True)
    )
    return ProjectInstance(
        name=instance.name, activities=activities, roles=instance.roles, workers=instance.workers
    )


def assert_feasible(instance: ProjectInstance, result: SimulationResult) -> None:
    realised, schedule = realised_instance(instance, result)
    assert validate_schedule(realised, schedule) == []
    assert execution_violations(instance, result) == []


def test_exact_replay_of_the_cpsat_optimum_of_tiny(tiny: ProjectInstance) -> None:
    solved = solve_cpsat(tiny, time_limit_s=10)
    assert solved.schedule is not None
    result = simulate(tiny, solved.schedule, NoReaction(), 3, pert=EXACT, disruptions=NONE)
    assert result.starts == solved.schedule.starts
    assert result.makespan == 7
    assert not result.truncated
    assert result.n_epochs == 2  # days 0 and 5
    assert result.total_cost == 14.0  # worker-days 2*3 + 2*2 + 1*4
    doubled = simulate(
        tiny, solved.schedule, NoReaction(), 3, pert=EXACT, disruptions=NONE, costs=[2.0]
    )
    assert doubled.total_cost == 28.0


def test_exact_replay_of_an_sgs_schedule_with_resource_delays(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    assert plan.starts != earliest_starts(eight)  # resources delay some activities
    result = simulate(eight, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE)
    assert result.starts == plan.starts
    assert result.makespan == plan.makespan(eight) == 7
    assert_feasible(eight, result)


def test_milestones_add_no_delay(build: Builder) -> None:
    # 0 -> 1 -> 3 (milestone) -> 2 -> 4: the milestone's successor has the smaller id.
    inst = build([0, 2, 1, 0, 0], [[0], [1], [1], [0], [0]], [[1], [3], [4], [2], []])
    plan = Schedule(starts=(0, 0, 2, 2, 3))
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE)
    assert result.starts == plan.starts
    assert result.finishes == (0, 2, 3, 2, 3)


def test_stochastic_durations_give_feasible_schedules(
    tiny: ProjectInstance, eight: ProjectInstance
) -> None:
    for instance in (tiny, eight):
        plan = lft_plan(instance)
        for seed in range(10):
            result = simulate(
                instance, plan, NoReaction(), seed, pert=PertParams(), disruptions=NONE
            )
            realised = with_durations(instance, result.work)
            assert validate_schedule(realised, Schedule(starts=result.starts)) == []
            assert all(
                s is not None and s >= p for s, p in zip(result.starts, plan.starts, strict=True)
            )
            assert not result.events


def test_same_seed_same_result_and_different_seeds_differ(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    runs = [
        simulate(eight, plan, NoReaction(), seed, pert=PertParams(), disruptions=BUSY)
        for seed in (1, 1, 2)
    ]
    assert runs[0] == runs[1]
    assert runs[0] != runs[2]


def test_common_random_numbers_across_policies_and_plans(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    late = Schedule(starts=tuple(s + 4 for s in plan.starts))
    for seed in range(5):
        base = simulate(eight, plan, NoReaction(), seed, pert=PertParams(), disruptions=BUSY)
        other = simulate(eight, plan, EmptyPolicy(), seed, pert=PertParams(), disruptions=BUSY)
        shifted = simulate(eight, late, NoReaction(), seed, pert=PertParams(), disruptions=BUSY)
        assert other == base  # same absence events, and here the whole run
        horizon = min(base.makespan, shifted.makespan)
        assert [e for e in base.events if isinstance(e, Absence) and e.day <= horizon] == [
            e for e in shifted.events if isinstance(e, Absence) and e.day <= horizon
        ]
        first = [(e.day, e.template) for e in base.events if isinstance(e, NewActivity)]
        second = [(e.day, e.template) for e in shifted.events if isinstance(e, NewActivity)]
        assert [x for x in first if x[0] <= horizon] == [x for x in second if x[0] <= horizon]


def test_absence_pauses_and_resumes_with_the_same_workers(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 5) needs both workers, B (p 2) one; B is planned for day 1 while A runs.
    inst = build([0, 5, 2, 0], [[0], [2], [1], [0]], [[1, 2], [3], [3], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 1, 5))
    onsets = {1: [AbsenceDraw(worker=1, length=2, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(onsets=onsets))
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, record_trace=True)
    # Paused on day 1, worker 0 released to B (days 1-2), back on day 3 = 1 + L, A resumes.
    a_segments = [(s.start, s.end, s.workers) for s in result.segments if s.activity == 1]
    assert a_segments == [(0, 1, (0, 1)), (3, 7, (0, 1))]
    assert [(s.start, s.end, s.workers) for s in result.segments if s.activity == 2] == [
        (1, 3, (0,))
    ]
    assert result.work[1] == 5  # completed work is kept
    assert result.finishes[1] == 7 and result.makespan == 7
    assert result.events == (Absence(day=1, worker=1, length=2, announced=1),)
    assert result.n_epochs == 3  # days 0, 1 (absence) and 5
    assert result.trace is not None
    assert [day.absent for day in result.trace[:4]] == [(), (1,), (1,), ()]
    assert_feasible(inst, result)


def test_random_absences_respect_the_announced_bound(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    absences = 0
    for seed in range(20):
        result = simulate(eight, plan, NoReaction(), seed, pert=PertParams(), disruptions=BUSY)
        for event in result.events:
            if isinstance(event, Absence):
                absences += 1
                assert 1 <= event.announced <= event.length
        assert_feasible(eight, result)
    assert absences > 20


def test_forced_work_increase_extends_the_duration(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst = build([0, 6, 0], [[0], [1], [0]], [[1], [2], []], capacities=(1,))
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(shocks={1: (2, 1.5)}))
    shocks_on = DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=0.5, lambda_n=0)
    plan = Schedule(starts=(0, 0, 6))
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=shocks_on)
    # After 2 work-days 4 units remain; ceil(4 * 1.5) = 6, so 2 + 6 = 8 work-days in total.
    assert result.events == (
        WorkIncrease(
            day=2, activity=1, work_done=2, factor=1.5, remaining_before=4, remaining_after=6
        ),
    )
    assert result.work[1] == 8
    assert result.finishes[1] == 8 and result.makespan == 8


def test_random_work_increases_follow_the_ceil_rule(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    params = DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=0.3, lambda_n=0)
    shocks = 0
    for seed in range(20):
        result = simulate(eight, plan, NoReaction(), seed, pert=PertParams(), disruptions=params)
        durations = ScenarioStreams(seed, eight, params, PertParams()).durations
        added = [0] * eight.n_activities
        for event in result.events:
            assert isinstance(event, WorkIncrease)
            shocks += 1
            assert 1.2 <= event.factor <= 2.0
            assert event.remaining_after == math.ceil(event.remaining_before * event.factor)
            added[event.activity] += event.remaining_after - event.remaining_before
        assert list(result.work) == [p + a for p, a in zip(durations, added, strict=True)]
    assert shocks > 10


def test_new_activities_keep_the_graph_acyclic(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    params = DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=0, lambda_n=0.15)
    inserted = 0
    for seed in range(20):
        result = simulate(eight, plan, NoReaction(), seed, pert=PertParams(), disruptions=params)
        new = [e for e in result.events if isinstance(e, NewActivity)]
        inserted += len(new)
        assert [e.activity for e in new] == list(range(8, 8 + len(new)))  # ids n+2, n+3, ...
        assert_feasible(eight, result)  # builds the extended graph, which must be acyclic
        starts = [s for s in result.starts if s is not None]
        finishes = [f for f in result.finishes if f is not None]
        assert len(starts) == len(finishes) == 8 + len(new)
        assert result.starts[7] == result.makespan == max(finishes)  # the sink completes last
        for e in new:
            assert result.finishes[e.predecessor] <= result.starts[e.activity]  # type: ignore[operator]
            assert result.finishes[e.activity] <= result.starts[e.successor]  # type: ignore[operator]
            assert result.starts[e.activity] >= e.day + 1  # type: ignore[operator]
    assert inserted > 10


def test_truncation_at_max_days(tiny: ProjectInstance) -> None:
    plan = lft_plan(tiny)  # makespan 7
    result = simulate(tiny, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, deadline=1)
    assert result.truncated
    assert result.max_days == 5 == result.makespan
    assert result.deadline_met is False
    assert result.starts[tiny.sink_id] is None


def test_observation_hides_hidden_quantities() -> None:
    hidden = {"remaining", "durations", "true_duration", "work", "return_day", "length"}
    hidden |= {"next_shock", "shock_factor", "events", "template"}
    assert not hidden & set(Observation.model_fields)
    assert not hidden & set(InsertedActivity.model_fields)


def test_observations_do_not_depend_on_true_durations(build: Builder) -> None:
    inst = build([0, 10, 0], [[0], [1], [0]], [[1], [2], []], capacities=(1,))
    plan = Schedule(starts=(0, 0, 10))
    by_duration = {ScenarioStreams(s, inst, NONE, PertParams()).durations[1]: s for s in range(50)}
    assert len(by_duration) >= 2 and min(by_duration) > 5
    views = []
    for seed in list(by_duration.values())[:2]:
        recorder = Recorder()
        simulate(inst, plan, recorder, seed, pert=PertParams(), disruptions=NONE)
        views.append([obs for obs in recorder.seen if obs.day <= 5])
    assert [obs.day for obs in views[0]] == [0, 5]
    assert views[0] == views[1]
    obs = views[0][-1]
    assert obs.status[1] == "running" and obs.work_done[1] == 5
    assert Observation.model_validate(obs.model_dump()) == obs


def test_result_round_trips_through_validation(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    for seed in range(5):
        result = simulate(
            eight, plan, Recorder(), seed, pert=PertParams(), disruptions=BUSY, record_trace=True
        )
        assert SimulationResult.model_validate(result.model_dump()) == result
