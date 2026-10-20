"""Mid-project rollouts: rebuilt engine states, rollout streams and the forecaster (spec 5.1)."""

import inspect
from collections.abc import Callable
from statistics import fmean
from typing import Any

import numpy as np
import pytest

from sentinel.forecasting import forecast as forecast_module
from sentinel.forecasting.deterministic import deterministic_forecast, nominal_world
from sentinel.forecasting.forecast import Forecast, Priors, forecast
from sentinel.forecasting.streams import RolloutStreams
from sentinel.model import ProjectInstance, Schedule
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import Run, simulate
from sentinel.simulation.events import AbsenceDraw, DisruptionParams, ScenarioStreams
from sentinel.simulation.state import (
    EngineState,
    Observation,
    SampledWorld,
    day_limit,
    state_from_observation,
)
from sentinel.simulation.uncertainty import PertParams, role_costs

Builder = Callable[..., ProjectInstance]

PERT = PertParams()
BUSY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1)
NO_SHOCKS = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.0, lambda_n=0.1)


def random_instance(build: Builder, seed: int, n: int = 15) -> ProjectInstance:
    """n real activities on three roles, each with up to two later successors."""
    rng = np.random.default_rng(seed)
    capacities = (3, 4, 5)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(0, 8, size=n).tolist(), 0]
    demands = [[0] * 3, *([int(rng.integers(0, c + 1)) for c in capacities] for _ in range(n))]
    return build(
        durations, [*demands, [0] * 3], [sorted(s) for s in successors], capacities=capacities
    )


def lft_plan(instance: ProjectInstance) -> Schedule:
    return serial_sgs(instance, lft_priorities(instance), lower_is_better=True)


def world_at(
    instance: ProjectInstance, plan: Schedule, seed: int, params: DisruptionParams, day: int
) -> Run | None:
    """A NoReaction world run stopped at step 3 of `day`; None if it finished before."""
    streams = ScenarioStreams(seed, instance, params, PERT)
    deadline = plan.makespan(instance) + 5
    state = EngineState(
        instance,
        plan,
        streams.durations,
        role_costs(instance, None),
        pert=PERT,
        disruptions=params,
        deadline=deadline,
        max_days=day_limit(instance, deadline),
    )
    run = Run(state, streams, NoReaction())
    for t in range(day):
        if run.close_day(t, run.open_day(t)):
            return None
    run.open_day(day)
    return run


def one_person_crews(build: Builder) -> ProjectInstance:
    """Two parallel chains of one-person activities on one role of capacity 2, so that an
    absence pauses an activity."""
    return build(
        [0, 4, 3, 5, 2, 6, 3, 4, 2, 0],
        [[0], [1], [1], [1], [1], [1], [1], [1], [1], [0]],
        [[1, 2], [3], [4], [5], [6], [7], [8], [9], [9], []],
        capacities=(2,),
    )


def stopped_worlds(
    build: Builder, params: DisruptionParams
) -> list[tuple[ProjectInstance, Schedule, int, Run]]:
    """World runs on three random instances and one with one-person crews, stopped at 25, 50
    and 75 % of the plan."""
    worlds = []
    instances = [random_instance(build, seed=i) for i in range(3)] + [one_person_crews(build)]
    for i, instance in enumerate(instances):
        plan = lft_plan(instance)
        for seed in range(6):
            for share in (0.25, 0.5, 0.75):
                day = int(share * plan.makespan(instance))
                run = world_at(instance, plan, 100 * i + seed, params, day)
                if run is not None:
                    worlds.append((instance, plan, 100 * i + seed, run))
    return worlds


SAME_FIELDS = (
    "day",
    "cost",
    "status",
    "start",
    "finish",
    "plan",
    "remaining",
    "done",
    "duration",
    "demands",
    "unit",
    "daily_cost",
    "successors",
    "pending",
    "eligible",
    "running",
    "present",
    "return_day",
    "absent_since",
    "announced",
    "busy",
    "idle",
    "role",
    "inserted",
    "work_increases",
    "max_days",
    "deadline",
)


def test_state_from_observation_rebuilds_the_engine_state(build: Builder) -> None:
    features = {"paused": 0, "partial": 0, "absent": 0, "inserted": 0, "shocked": 0}
    for _, _, _, run in stopped_worlds(build, BUSY):
        true = run.state
        obs = true.observe()
        rebuilt = state_from_observation(obs, true.hidden())
        for name in SAME_FIELDS:
            assert getattr(rebuilt, name) == getattr(true, name), name
        for j, status in enumerate(true.status):
            if status in ("running", "paused"):
                assert rebuilt.assigned[j] == true.assigned[j]
                assert rebuilt.working[j] == true.working[j]
            if status == "running":
                assert (rebuilt.rate[j], rebuilt.work_cost[j]) == (true.rate[j], true.work_cost[j])
                features["partial"] += 0 < true.rate[j] < true.unit[j]
        features["paused"] += "paused" in true.status
        features["absent"] += not all(true.present)
        features["inserted"] += bool(true.inserted)
        features["shocked"] += bool(true.work_increases)
        assert rebuilt.observe() == obs
    assert all(count > 0 for count in features.values()), features


def test_resumed_state_continues_like_the_world(build: Builder) -> None:
    """With the world's own streams (no D2, whose counters restart) a rebuilt state finishes
    exactly as the world does, absences and new activities after the day included."""
    for instance, plan, seed, run in stopped_worlds(build, NO_SHOCKS):
        whole = simulate(
            instance,
            plan,
            NoReaction(),
            seed,
            pert=PERT,
            disruptions=NO_SHOCKS,
            deadline=plan.makespan(instance) + 5,
        )
        state = state_from_observation(run.state.observe(), run.state.hidden())
        Run(state, ScenarioStreams(seed, instance, NO_SHOCKS, PERT), NoReaction()).resume()
        assert state.start == list(whole.starts)
        assert state.finish == list(whole.finishes)
        assert state.cost == whole.total_cost


def test_perfect_information_rollouts_reproduce_the_true_makespan(build: Builder) -> None:
    """True hidden state and no disruptions after the day in world and forecast: every rollout
    ends exactly when the world does."""
    for instance, _, seed, run in stopped_worlds(build, BUSY):
        state = run.state
        obs, truth = state.observe(), state.hidden()
        # The world goes on without future disruptions: no onsets, arrivals or D2 shocks.
        run.streams = ScenarioStreams(seed, instance, DisruptionParams.none(), PERT)
        run.shocks = False
        state.next_shock = [0] * len(state.next_shock)
        if not run.close_day(state.day, True):
            run.days(state.day + 1)
        start = state.start[state.sink]
        true_makespan = state.max_days if start is None else start
        result = forecast(
            obs,
            Schedule(starts=obs.plan),
            n_rollouts=5,
            seed=seed,
            include_future_disruptions=False,
            _true_world=truth,
        )
        assert result.makespans == (true_makespan,) * 5


def test_rollout_streams_do_not_depend_on_query_order() -> None:
    def streams() -> RolloutStreams:
        seq = np.random.SeedSequence(5)
        return RolloutStreams(seq, BUSY, PERT, day=10, n_original=6, return_day=[-1, 14, -1, 12])

    forward, scrambled = streams(), streams()
    onsets = {d: forward.absence_onsets(d) for d in range(11, 400)}
    arrivals = {d: forward.new_activity(d) for d in range(11, 400)}
    shocks = {j: forward.work_shock(j, 1, 500) for j in range(6)}
    for d in (399, 57, 11, 200):
        assert scrambled.new_activity(d) == arrivals[d]
        assert scrambled.absence_onsets(d) == onsets[d]
    for j in (5, 2, 0, 1, 4, 3):
        assert scrambled.work_shock(j, 1, 500) == shocks[j]
    assert any(onsets.values()) and any(arrivals.values()) and any(shocks.values())
    assert all(w != 1 for d in range(11, 15) for w, _, _ in onsets[d])  # back on day 14
    assert all(w != 3 for d in range(11, 13) for w, _, _ in onsets[d])  # back on day 12


def test_rollout_streams_follow_the_event_distributions() -> None:
    """Gaps to the next event are geometric, as runs of daily Bernoullis (spec section 2.2)."""
    first_gap, second_gap, lengths, announced = [], [], [], []
    shock_gap, factors, arrival_gap = [], [], []
    for i in range(500):
        streams = RolloutStreams(
            np.random.SeedSequence(i), BUSY, PERT, day=10, n_original=6, return_day=[-1, 20] * 5
        )
        by_worker: dict[int, list[tuple[int, int, int]]] = {}
        for d in range(11, 400):
            for w, length, low in streams.absence_onsets(d):
                by_worker.setdefault(w, []).append((d, length, low))
                lengths.append(length)
                announced.append(low)
                assert 1 <= low <= length
        for w, onsets in by_worker.items():
            resume = 11 if w % 2 == 0 else 21
            first_gap.append(onsets[0][0] - resume + 1)
            if len(onsets) > 1:
                (day, length, _), (later, _, _) = onsets[:2]
                second_gap.append(later - (day + length + 1) + 1)  # no draw on the return day
        for j in range(6):
            shock = streams.work_shock(j, 1, 10**6)
            assert shock is not None
            k, factor = shock
            shock_gap.append(k)
            factors.append(factor)
            later_shock = streams.work_shock(j, k + 1, 10**6)
            assert later_shock is not None and later_shock[0] > k
        arrival_gap.append(next(d for d in range(11, 1000) if streams.new_activity(d)) - 10)
    assert abs(fmean(first_gap) - 1 / BUSY.lambda_a) < 1.0  # SE 0.2
    assert abs(fmean(second_gap) - 1 / BUSY.lambda_a) < 1.0
    assert abs(fmean(lengths) - BUSY.mean_absence) < 0.15  # SE 0.02
    assert abs(fmean(announced) - (BUSY.mean_absence + 1) / 2) < 0.1
    assert abs(fmean(shock_gap) - 1 / BUSY.lambda_s) < 0.8  # SE 0.17
    assert min(factors) >= BUSY.f_low and max(factors) < BUSY.f_high
    assert abs(fmean(factors) - (BUSY.f_low + BUSY.f_high) / 2) < 0.02
    assert abs(fmean(arrival_gap) - 1 / BUSY.lambda_n) < 2.0  # SE 0.4


def observation_with_absences(build: Builder) -> tuple[ProjectInstance, Observation]:
    """An observation on day 8 of a world run with absent workers and running activities."""
    instance = random_instance(build, seed=7)
    plan = lft_plan(instance)
    for seed in range(50):
        run = world_at(instance, plan, seed, BUSY, 8)
        if run is not None and not all(run.state.present) and run.state.running:
            return instance, run.state.observe()
    raise AssertionError("no suitable observation")


def test_forecasts_with_the_same_seed_share_samples_across_plans(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    logs: list[dict[str, Any]] = []

    class Recording(RolloutStreams):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.log: dict[str, Any] = {"returns": kwargs["return_day"], "onsets": {}, "new": {}}
            logs.append(self.log)

        def absence_onsets(self, day: int) -> tuple[AbsenceDraw, ...]:
            self.log["onsets"][day] = tuple(super().absence_onsets(day))
            return self.log["onsets"][day]  # type: ignore[no-any-return]

        def new_activity(self, day: int) -> Any:
            self.log["new"][day] = super().new_activity(day)
            return self.log["new"][day]

    monkeypatch.setattr(forecast_module, "RolloutStreams", Recording)
    _, obs = observation_with_absences(build)
    late = tuple(
        s + 3 if status == "unstarted" else s
        for s, status in zip(obs.plan, obs.status, strict=True)
    )
    first = forecast(obs, Schedule(starts=obs.plan), n_rollouts=30, seed=4)
    first_logs = logs.copy()
    logs.clear()
    second = forecast(obs, Schedule(starts=late), n_rollouts=30, seed=4)
    assert first.makespans != second.makespans
    assert len(first_logs) == len(logs) == 30
    for a, b in zip(first_logs, logs, strict=True):
        assert a["returns"] == b["returns"]  # the same sampled world
        common = a["onsets"].keys() & b["onsets"].keys()
        assert common and all(a["onsets"][d] == b["onsets"][d] for d in common)
        assert all(a["new"][d] == b["new"][d] for d in a["new"].keys() & b["new"].keys())
    assert any(any(log["onsets"].values()) for log in logs)


def test_forecast_sees_only_the_observation(build: Builder) -> None:
    """Hidden state reaches the forecasters only through the explicit `_true_world` test hook;
    `priors` are assumptions of the same kind as the observation's `pert` and `disruptions`."""
    names = list(inspect.signature(forecast).parameters)
    assert names == [
        "observation",
        "plan",
        "n_rollouts",
        "seed",
        "include_future_disruptions",
        "priors",
        "_true_world",
    ]
    assert list(inspect.signature(deterministic_forecast).parameters) == [
        "observation",
        "plan",
        "seed",
    ]
    assert set(Priors.model_fields) == {"pert", "disruptions"}
    instance, obs = observation_with_absences(build)
    plan = Schedule(starts=obs.plan)
    run = world_at(instance, lft_plan(instance), 0, BUSY, 3)
    assert run is not None
    for hidden in (
        run.state,
        run.state.hidden(),
        simulate(instance, lft_plan(instance), NoReaction(), 0, pert=PERT, disruptions=BUSY),
    ):
        with pytest.raises(TypeError):
            forecast(hidden, plan, n_rollouts=1, seed=0)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            deterministic_forecast(hidden, plan, seed=0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        forecast(obs, obs.plan, n_rollouts=1, seed=0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        deterministic_forecast(obs, obs.plan, seed=0)  # type: ignore[arg-type]
    hidden_fields = {"remaining", "return_day", "durations", "next_shock", "shock_factor"}
    assert not hidden_fields & set(Observation.model_fields)
    assert not hidden_fields & set(Schedule.model_fields)
    assert not hidden_fields & set(Priors.model_fields)


def test_forecast_statistics_and_determinism(build: Builder) -> None:
    summary = Forecast(
        day=0,
        seed=0,
        n_rollouts=10,
        include_future_disruptions=True,
        makespans=tuple(range(10, 20)),
        truncated=0,
        fallbacks=0,
        wall_time_s=0.0,
    )
    assert summary.mean == 14.5
    assert summary.quantiles == (10, 14, 18)
    assert summary.p_on_time(14) == 0.5
    _, obs = observation_with_absences(build)
    plan = Schedule(starts=obs.plan)
    runs = [forecast(obs, plan, n_rollouts=20, seed=s) for s in (1, 1, 2)]
    assert runs[0].makespans == runs[1].makespans != runs[2].makespans
    assert runs[0].day == obs.day and runs[0].fallbacks == 0
    assert obs.deadline is not None
    assert runs[0].truncated == sum(c == 5 * obs.deadline for c in runs[0].makespans)
    with pytest.raises(ValueError):
        forecast(obs, plan, n_rollouts=0, seed=1)
    with pytest.raises(ValueError):
        forecast(obs, Schedule(starts=obs.plan[:-1]), n_rollouts=1, seed=1)


def test_sampled_worlds_are_the_only_hidden_input(build: Builder) -> None:
    """Rebuilding needs one remaining work per activity and one return day per worker."""
    _, obs = observation_with_absences(build)
    world = SampledWorld(tuple([1.0] * len(obs.status)), tuple([-1] * len(obs.present)))
    with pytest.raises(ValueError):
        state_from_observation(obs, world._replace(remaining=world.remaining[:-1]))
    with pytest.raises(ValueError):
        state_from_observation(obs, world._replace(return_day=world.return_day[:-1]))


def test_deterministic_forecast_is_exact_without_uncertainty(build: Builder) -> None:
    """With X = 1 and no disruptions the nominal state is the true one, so the plan-based
    forecast (spec section 5.2) gives the true makespan from every day of the run."""
    exact, quiet = PertParams(a=1.0, m=1.0, b=1.0), DisruptionParams.none()
    instances = [random_instance(build, seed=i) for i in range(4)] + [one_person_crews(build)]
    checked = 0
    for instance in instances:
        plan = lft_plan(instance)
        world = simulate(
            instance,
            plan,
            NoReaction(),
            0,
            pert=exact,
            disruptions=quiet,
            deadline=plan.makespan(instance) + 5,
            observe_days=range(plan.makespan(instance) + 1),
        )
        assert len(world.observations) == world.makespan + 1
        for obs in world.observations:
            result = deterministic_forecast(obs, Schedule(starts=obs.plan), seed=3)
            assert result.makespans == (world.makespan,)
            assert (result.n_rollouts, result.truncated, result.fallbacks) == (1, 0, 0)
            assert result.p_on_time(world.makespan) == 1.0
            assert result.p_on_time(world.makespan - 1) == 0.0
            checked += 1
    assert checked > 50


def test_nominal_world_follows_the_spec(build: Builder) -> None:
    """Hand-computed nominal remaining work (crew-member days) and return days (spec 5.2)."""
    instance = build(
        [0, 4, 2, 3, 2, 0],
        [[0], [2], [1], [1], [1], [0]],
        [[1, 2, 3, 4], [5], [5], [5], [5], []],
        capacities=(5,),
    )
    start = EngineState(
        instance,
        lft_plan(instance),
        [0] * 6,
        role_costs(instance, None),
        pert=PERT,
        disruptions=BUSY,
        deadline=20,
        max_days=100,
    ).observe()
    obs = start.model_copy(
        update={
            "day": 6,
            "status": ("done", "running", "paused", "running", "unstarted", "unstarted"),
            "work_done": (0.0, 2.5, 3.0, 4.0, 0.0, 0.0),
            "assigned": ((), (0, 1), (2,), (3,), (), ()),
            # Activity 1: shock F = 1.5 after 1 full-crew day; activity 3: F = 3 after 3 days.
            "work_increases": ((1, 1.0, 1.5), (3, 3.0, 3.0)),
            "present": (True, False, False, True, True),
            "absent_since": (None, 5, 2, None, None),
            "announced": (None, 4, 1, None, None),
        }
    )
    world = nominal_world(obs)
    # 1: max(8 - 2, 1) * 1.5 = 9, then max(9 - (5 - 2), 1) = 6; 2: overran, max(2 - 3, 1) = 1;
    # 3: max(3 - 3, 1) * 3 = 3, then 3 - (4 - 3) = 2; 4: unstarted, p_j M_j = 2.
    assert world.remaining == (0.0, 6.0, 1.0, 2.0, 2.0, 0.0)
    # Worker 1: 5 + max(4, 2) = 9 (announced bound); worker 2: 2 + max(1, 5) = 7 (tomorrow).
    assert world.return_day == (-1, 9, 7, -1, -1)
    assert world.fallbacks == 0
    result = deterministic_forecast(obs, Schedule(starts=obs.plan), seed=0)
    assert result.makespans[0] > obs.day and not result.include_future_disruptions


def test_priors_replace_the_forecasters_assumptions(build: Builder) -> None:
    """The observation's own priors change nothing; zero rates switch the future off; exact
    durations and no disruptions from day 0 turn every rollout into the nominal run."""
    instance, obs = observation_with_absences(build)
    plan = Schedule(starts=obs.plan)
    own = Priors(pert=obs.pert, disruptions=obs.disruptions)
    base = forecast(obs, plan, n_rollouts=30, seed=5)
    assert forecast(obs, plan, n_rollouts=30, seed=5, priors=own).makespans == base.makespans
    zero_rates = {"lambda_a": 0.0, "lambda_s": 0.0, "lambda_n": 0.0}  # E[L] kept for the belief
    silent = Priors(pert=obs.pert, disruptions=obs.disruptions.model_copy(update=zero_rates))
    no_future = forecast(obs, plan, n_rollouts=30, seed=5, include_future_disruptions=False)
    assert forecast(obs, plan, n_rollouts=30, seed=5, priors=silent).makespans == (
        no_future.makespans
    )
    assert no_future.makespans != base.makespans
    lft = lft_plan(instance)
    day0 = simulate(
        instance,
        lft,
        NoReaction(),
        1,
        pert=PERT,
        disruptions=DisruptionParams.none(),
        deadline=lft.makespan(instance) + 5,
        observe_days=(0,),
    ).observations[0]
    nominal = deterministic_forecast(day0, lft, seed=2).makespans[0]
    exact = Priors(pert=PertParams(a=1.0, m=1.0, b=1.0), disruptions=DisruptionParams.none())
    assert set(forecast(day0, lft, n_rollouts=20, seed=2, priors=exact).makespans) == {nominal}
    assert len(set(forecast(day0, lft, n_rollouts=20, seed=2).makespans)) > 1
