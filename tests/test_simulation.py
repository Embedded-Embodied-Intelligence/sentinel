"""Daily execution semantics of the simulator (spec sections 2-3, 3.1)."""

from collections.abc import Callable, Collection, Sequence

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


def test_zero_duration_activities_complete_early_so_projects_can_finish_early(
    build: Builder, tiny: ProjectInstance
) -> None:
    # 0 -> 1 (p 2) -> 2 (milestone) -> 3 (p 3) -> 4; the plan leaves slack before 2, 3 and 4.
    inst = build([0, 2, 0, 3, 0], [[0], [1], [0], [1], [0]], [[1], [2], [3], [4], []])
    plan = Schedule(starts=(0, 0, 4, 5, 10))
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE)
    # The milestone completes when 1 finishes, 3 still waits for its planned start (railway),
    # and the sink completes when 3 finishes (spec 3.1 c-d).
    assert result.starts == (0, 0, 2, 5, 8)
    assert result.makespan == 8 < plan.makespan(inst)
    assert_feasible(inst, result)
    # Without disruptions and with X = 1, a late sink no longer delays the project.
    late_sink = Schedule(starts=(*lft_plan(tiny).starts[:-1], 12))
    finished = simulate(tiny, late_sink, NoReaction(), 0, pert=EXACT, disruptions=NONE)
    assert finished.makespan == lft_plan(tiny).makespan(tiny) == 7 < late_sink.makespan(tiny)


def test_stochastic_durations_give_feasible_schedules(
    tiny: ProjectInstance, eight: ProjectInstance
) -> None:
    for instance in (tiny, eight):
        plan = lft_plan(instance)
        for seed in range(10):
            result = simulate(
                instance, plan, NoReaction(), seed, pert=PertParams(), disruptions=NONE
            )
            realised = with_durations(instance, [round(w) for w in result.work])
            assert validate_schedule(realised, Schedule(starts=result.starts)) == []
            # Railway starts for p_j > 0 only; milestones and the sink may complete early.
            assert all(
                s is not None and s >= p
                for s, p, act in zip(result.starts, plan.starts, instance.activities, strict=True)
                if act.duration > 0
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


def segments_of(result: SimulationResult, j: int) -> list[tuple[int, int, tuple[int, ...]]]:
    return [(s.start, s.end, s.workers) for s in result.segments if s.activity == j]


def absent_member_run(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> tuple[ProjectInstance, SimulationResult]:
    """A (p 5) needs both workers, B (p 2) one and is planned for day 1; worker 1 is out on
    days 1-2."""
    inst = build([0, 5, 2, 0], [[0], [2], [1], [0]], [[1, 2], [3], [3], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 1, 5))
    onsets = {1: [AbsenceDraw(worker=1, length=2, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(onsets=onsets))
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, record_trace=True)
    return inst, result


def test_absent_member_slows_the_crew_and_stays_reserved(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst, result = absent_member_run(build, monkeypatch)
    # A goes on at rho = 1/2 with worker 0, who is not released to B (spec 3.1 a): e_A = 1,
    # 1.5, 2, 3, 4, 5, so F_A = 6, and B starts only then.
    assert segments_of(result, 1) == [(0, 1, (0, 1)), (1, 3, (0,)), (3, 6, (0, 1))]
    assert segments_of(result, 2) == [(6, 8, (0,))]
    assert result.crews[1] == (0, 1)
    assert result.work[1] == 5  # completed work is kept
    assert result.finishes[1] == 6 and result.makespan == 8
    assert result.total_cost == 12.0  # worker-days worked: A 2 + 2 + 6, B 2; absent ones free
    assert result.events == (Absence(day=1, worker=1, length=2, announced=1),)
    assert result.n_epochs == 4  # days 0, 1 (absence), 3 (return) and 5
    assert result.trace is not None
    assert [day.absent for day in result.trace[:4]] == [(), (1,), (1,), ()]
    assert result.trace[1].working == ((1, (0,)),)  # B waits although worker 0 is present
    assert_feasible(inst, result)


def test_a_return_day_is_a_decision_epoch(build: Builder, monkeypatch: pytest.MonkeyPatch) -> None:
    # A (p 6) runs with worker 0; worker 1 is idle. Worker 1 is out on days 1-2 and worker 0 on
    # day 4. With T_r = 10 the epochs are day 0, the onsets on days 1 and 4, and the returns on
    # day 3 (to no crew) and day 5 (back to A's crew; spec section 3.1 g). A pauses on day 4.
    inst = build([0, 6, 0], [[0], [1], [0]], [[1], [2], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 6))
    onsets = {
        1: [AbsenceDraw(worker=1, length=2, announced=2)],
        4: [AbsenceDraw(worker=0, length=1, announced=1)],
    }
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(onsets=onsets))
    recorder = Recorder()
    result = simulate(
        inst, plan, recorder, 0, pert=EXACT, disruptions=NONE, review_period=10, record_trace=True
    )
    assert result.finishes[1] == 7 and result.makespan == 7
    assert result.trace is not None
    assert [day.day for day in result.trace if day.epoch] == [0, 1, 3, 4, 5]
    assert result.n_epochs == 5 and [obs.day for obs in recorder.seen] == [0, 1, 3, 4, 5]
    passive = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, review_period=10)
    assert passive.n_epochs == 5 and passive.makespan == 7


def test_feasibility_checks_count_reserved_absent_members(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst, result = absent_member_run(build, monkeypatch)
    # B on days 1-2 with worker 0 would overbook the role: A still reserves absent worker 1.
    early_b = result.model_copy(update={"starts": (0, 0, 1, 8), "finishes": (0, 6, 3, 8)})
    realised, schedule = realised_instance(inst, early_b)
    assert [(v.kind, v.time) for v in validate_schedule(realised, schedule)] == [
        ("resource", 1),
        ("resource", 2),
    ]
    problems = execution_violations(inst, early_b)
    assert "worker 0 is in the crews of 1 and 2 on day 1" in problems
    assert "activity 2 works on day 6 outside its reservation" in problems
    # An absence on a worked day: worker 0 would have worked while absent.
    absent = Absence(day=4, worker=0, length=1, announced=1)
    late_absence = result.model_copy(update={"events": (*result.events, absent)})
    assert execution_violations(inst, late_absence) == [
        "activity 1 works with (0, 1) on day 4, present (1,)"
    ]


def test_one_person_activity_pauses_and_resumes_with_the_same_worker(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 4) and B (p 2) need one worker each of a role with two; both start on day 0, and
    # A's worker 0 is out on days 1-2. B ends on day 2, yet its worker 1 does not take over A.
    inst = build([0, 4, 2, 0], [[0], [1], [1], [0]], [[1, 2], [3], [3], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 0, 4))
    onsets = {1: [AbsenceDraw(worker=0, length=2, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(onsets=onsets))
    recorder = Recorder()
    result = simulate(inst, plan, recorder, 0, pert=EXACT, disruptions=NONE, review_period=1)
    statuses = [obs.status[1] for obs in recorder.seen[:4]]
    assert statuses == ["unstarted", "paused", "paused", "running"]
    assert [obs.work_done[1] for obs in recorder.seen] == [0, 1, 1, 1, 2, 3, 4]  # work kept
    assert segments_of(result, 1) == [(0, 1, (0,)), (3, 6, (0,))]
    assert segments_of(result, 2) == [(0, 2, (1,))]
    assert result.crews[1] == (0,)
    assert result.finishes[1] == 6 and result.makespan == 6
    assert_feasible(inst, result)


@pytest.mark.parametrize(("p", "finish"), [(4, 5), (5, 7)])
def test_partial_crew_progresses_at_the_present_share(
    build: Builder, monkeypatch: pytest.MonkeyPatch, p: int, finish: int
) -> None:
    # A crew of four (M_j = 4); member 3 is out from day 1 to beyond the end. Dispatch takes
    # present workers only, so day 0 has the full crew and then rho_j = 3/4: with P_j = 4,
    # e_j = 1, 1.75, 2.5, 3.25, 4 and F = 5; with P_j = 5 the last 4 full-crew days take
    # ceil(4 / 0.75) = 6 days, so F = 7.
    inst = build([0, p, 0], [[0], [4], [0]], [[1], [2], []], capacities=(4,))
    plan = Schedule(starts=(0, 0, p))
    onsets = {1: [AbsenceDraw(worker=3, length=30, announced=30)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(onsets=onsets))
    recorder = Recorder()
    result = simulate(inst, plan, recorder, 0, pert=EXACT, disruptions=NONE, review_period=1)
    assert [obs.work_done[1] for obs in recorder.seen] == [0] + [
        1 + 0.75 * d for d in range(finish)
    ]
    assert recorder.seen[2].assigned[1] == (0, 1, 2, 3)  # the absent member stays in the crew
    assert recorder.seen[2].present[3] is False
    assert segments_of(result, 1) == [(0, 1, (0, 1, 2, 3)), (1, finish, (0, 1, 2))]
    assert result.finishes[1] == finish == result.makespan
    assert result.total_cost == 4 + 3 * (finish - 1)
    assert_feasible(inst, result)


def test_whole_crew_absent_pauses_and_resumes_at_the_reduced_rate(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A crew of four of the five workers leaves on day 1; they return on days 3, 4, 4 and 5.
    inst = build([0, 4, 0], [[0], [4], [0]], [[1], [2], []], capacities=(5,))
    plan = Schedule(starts=(0, 0, 4))
    lengths = (2, 3, 3, 4)
    onsets = {1: [AbsenceDraw(worker=w, length=n, announced=1) for w, n in enumerate(lengths)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_streams(onsets=onsets))
    recorder = Recorder()
    result = simulate(inst, plan, recorder, 0, pert=EXACT, disruptions=NONE, review_period=1)
    # No progress on days 1-2; from the first return rho = 1/4, then 3/4, then 1.
    statuses = [obs.status[1] for obs in recorder.seen[:4]]
    assert statuses == ["unstarted", "paused", "paused", "running"]
    assert [obs.work_done[1] for obs in recorder.seen] == [0, 1, 1, 1, 1.25, 2, 3, 4]
    assert segments_of(result, 1) == [
        (0, 1, (0, 1, 2, 3)),
        (3, 4, (0,)),
        (4, 5, (0, 1, 2)),
        (5, 7, (0, 1, 2, 3)),
    ]
    assert result.finishes[1] == 7
    assert result.total_cost == 4 + 1 + 3 + 4 + 4
    assert all(4 not in s.workers for s in result.segments)  # nobody is reassigned
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
    # The shock of the second work day (day 1) comes before its progress: 5 full-crew days
    # remain and become 5 * 1.5 = 7.5, so 1 + 7.5 = 8.5 in total, done with the ninth day.
    assert result.events == (
        WorkIncrease(
            day=1,
            activity=1,
            work_day=2,
            work_done=1.0,
            factor=1.5,
            remaining_before=5.0,
            remaining_after=7.5,
        ),
    )
    assert result.work[1] == 8.5
    assert result.finishes[1] == 9 and result.makespan == 9
    assert result.n_epochs == 3  # days 0 and 5, and day 2 after the shock


def test_work_increase_can_hit_a_one_day_activity(build: Builder) -> None:
    inst = build([0, 1, 0], [[0], [1], [0]], [[1], [2], []], capacities=(1,))
    always = DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=1, lambda_n=0)
    plan = Schedule(starts=(0, 0, 1))
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=always, deadline=10)
    shocks = [e for e in result.events if isinstance(e, WorkIncrease)]
    # Drawn on the first work day before progress (spec 2.2): nothing done yet, one day left.
    first = shocks[0]
    assert (first.day, first.activity, first.work_day, first.work_done) == (0, 1, 1, 0.0)
    assert first.remaining_before == 1.0 and first.remaining_after == first.factor
    # lambda_S = 1 hits every work day until the remaining work runs out.
    assert [(e.day, e.work_day) for e in shocks] == [(d, d + 1) for d in range(len(shocks))]
    assert result.finishes[1] == len(shocks) >= 2 and result.work[1] > 1
    assert result.n_epochs == result.makespan + 1  # day 0 and every day after a shock


def test_random_work_increases_scale_the_remaining_work(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    params = DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=0.3, lambda_n=0)
    shocks = 0
    for seed in range(20):
        result = simulate(eight, plan, NoReaction(), seed, pert=PertParams(), disruptions=params)
        durations = ScenarioStreams(seed, eight, params, PertParams()).durations
        added = [0.0] * eight.n_activities
        for event in result.events:
            assert isinstance(event, WorkIncrease)
            shocks += 1
            assert 1.2 <= event.factor <= 2.0
            assert event.remaining_after == pytest.approx(event.remaining_before * event.factor)
            added[event.activity] += event.remaining_after - event.remaining_before
        expected = [p + a for p, a in zip(durations, added, strict=True)]
        assert list(result.work) == pytest.approx(expected)
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
            # Planned no earlier than the next day; a zero-duration copy completes at once.
            earliest = e.day + 1 if e.duration > 0 else e.day
            assert result.starts[e.activity] >= earliest  # type: ignore[operator]
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


def busy_run(
    instance: ProjectInstance,
    seed: int,
    policy: NoReaction | Recorder,
    *,
    review_period: int = 5,
    observe_days: Collection[int] = (),
) -> SimulationResult:
    """A run of the LFT plan with every disruption on, a deadline and the trace."""
    plan = lft_plan(instance)
    return simulate(
        instance,
        plan,
        policy,
        seed,
        pert=PertParams(),
        disruptions=BUSY,
        deadline=plan.makespan(instance) + 3,
        review_period=review_period,
        record_trace=True,
        observe_days=observe_days,
    )


def test_observing_days_leaves_the_results_unchanged(
    eight: ProjectInstance, tiny: ProjectInstance
) -> None:
    """Checkpoint observations (spec section 5.2) are a by-product: the result, events and trace
    included, is identical with and without them, and they are the step-3 view of their day."""
    checked = 0
    for instance in (eight, tiny):
        for seed in range(8):
            for policy in (NoReaction, Recorder):
                plain = busy_run(instance, seed, policy())
                every_day = range(plain.max_days + 1)
                observed = busy_run(instance, seed, policy(), observe_days=every_day)
                assert observed.model_dump() == plain.model_dump()
                assert "observations" not in plain.model_dump() and plain.observations == ()
                assert [o.day for o in observed.observations] == list(range(plain.makespan + 1))
                some = busy_run(instance, seed, policy(), observe_days={0, 3, plain.max_days + 7})
                assert [o.day for o in some.observations] == [0, 3]
                assert some.model_dump() == plain.model_dump()
                recorder = Recorder()  # every day is an epoch, so it sees every step-3 view
                busy_run(instance, seed, recorder, review_period=1)
                assert observed.observations == tuple(recorder.seen)
                checked += 1
    assert checked == 32


def test_result_round_trips_through_validation(eight: ProjectInstance) -> None:
    plan = lft_plan(eight)
    for seed in range(5):
        result = simulate(
            eight, plan, Recorder(), seed, pert=PertParams(), disruptions=BUSY, record_trace=True
        )
        assert SimulationResult.model_validate(result.model_dump()) == result
