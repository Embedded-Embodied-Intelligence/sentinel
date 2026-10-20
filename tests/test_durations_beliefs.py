"""Exact duration pmf and the belief over the hidden state (spec sections 2.1 and 5.1)."""

import math
from collections.abc import Callable
from statistics import fmean
from typing import Any

import numpy as np
import pytest

from sentinel.forecasting.beliefs import MAX_ABSENCE, Belief, absence_posterior, sample_world
from sentinel.forecasting.durations import IntegerPmf, duration_pmf
from sentinel.model import ProjectInstance, Schedule
from sentinel.policies.base import Decision
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import EngineState, Observation
from sentinel.simulation.uncertainty import PertParams, pert_multipliers, realised_duration

Builder = Callable[..., ProjectInstance]

BUSY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1)


class Recorder:
    """Test-only policy that keeps every observation and never intervenes."""

    def __init__(self) -> None:
        self.seen: list[Observation] = []

    def decide(self, observation: Observation) -> Decision:
        self.seen.append(observation)
        return Decision()


def initial_observation(
    instance: ProjectInstance, plan: Schedule, disruptions: DisruptionParams = BUSY
) -> Observation:
    """The observation of day 0 before any event (durations are hidden, so any will do)."""
    state = EngineState(
        instance,
        plan,
        [0] * instance.n_activities,
        [1.0] * len(instance.roles),
        pert=PertParams(),
        disruptions=disruptions,
        deadline=None,
        max_days=100,
    )
    return state.observe()


def observed(base: Observation, **changes: Any) -> Observation:
    """`base` with some fields replaced and validated again."""
    return Observation.model_validate(base.model_copy(update=changes).model_dump())


@pytest.mark.parametrize(
    "params",
    [PertParams(), PertParams(a=0.7, m=1.0, b=1.5)],
    ids=["closed-form", "simpson"],
)
def test_duration_pmf_matches_the_sampler(params: PertParams) -> None:
    multipliers = pert_multipliers(10**6, np.random.default_rng(11), params).tolist()
    for nominal in (1, 3, 10):
        pmf = duration_pmf(nominal, params)
        assert math.fsum(pmf.probs) == pytest.approx(1.0, abs=1e-12)
        assert min(pmf.probs) > 0
        sampled = [realised_duration(nominal, x) for x in multipliers]
        assert abs(pmf.mean - fmean(sampled)) < 0.01
        counts = np.bincount(sampled, minlength=pmf.last + 1)
        assert counts[: pmf.first].sum() == 0 and len(counts) == pmf.last + 1
        assert np.abs(counts[pmf.first :] / len(sampled) - pmf.probs).max() < 0.003


def test_duration_pmf_edge_cases() -> None:
    assert (duration_pmf(0, PertParams()).first, duration_pmf(0, PertParams()).probs) == (0, (1.0,))
    exact = duration_pmf(7, PertParams(a=1.0, m=1.0, b=1.0))
    assert (exact.first, exact.probs) == (7, (1.0,))
    halved = duration_pmf(1, PertParams(a=0.5, m=0.5, b=0.5))  # max(1, round(0.5)) = 1
    assert (halved.first, halved.probs) == (1, (1.0,))
    assert duration_pmf(4, PertParams()) is duration_pmf(4, PertParams())  # cached
    with pytest.raises(ValueError):
        duration_pmf(-1, PertParams())


def test_integer_pmf_inverse_cdf_and_conditioning() -> None:
    pmf = IntegerPmf(3, [1.0, 0.0, 3.0])  # P(3) = 1/4, P(4) = 0, P(5) = 3/4
    assert [pmf.sample(u) for u in (0.0, 0.2499, 0.25, 0.9999)] == [3, 3, 5, 5]
    assert pmf.mean == pytest.approx(4.5)
    tail = pmf.at_least(4)
    assert tail is not None and (tail.first, tail.probs) == (4, (0.0, 1.0))
    assert all(tail.sample(u) == 5 for u in np.linspace(0, 0.999, 50))
    assert pmf.at_least(1) is pmf
    assert IntegerPmf(1, [1.0, 0.0]).at_least(2) is None
    with pytest.raises(ValueError):
        IntegerPmf(0, [0.0, 0.0])


def test_conditional_durations_exceed_the_work_done(build: Builder) -> None:
    """Hidden durations of started activities are sampled given P_j > e_j (no D2 shocks)."""
    inst = build(
        [0, 6, 4, 9, 0],
        [[0, 0], [2, 1], [1, 1], [1, 2], [0, 0]],
        [[1, 2], [3], [3], [4], []],
        capacities=(3, 3),
    )
    plan = Schedule(starts=(0, 0, 0, 6, 15))
    recorder = Recorder()
    params = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.0, lambda_n=0.0)
    for seed in range(20):
        simulate(inst, plan, recorder, seed, pert=PertParams(), disruptions=params, review_period=1)
    started = 0
    for obs in recorder.seen[::7]:
        belief = Belief(obs)
        assert belief.fallbacks == 0
        rng = np.random.default_rng(obs.day)
        for _ in range(20):
            world = belief.sample(rng)
            for j, status in enumerate(obs.status):
                unit = sum(inst.activities[j].demands) or 1
                pmf = duration_pmf(inst.activities[j].duration, PertParams())
                if status == "done":
                    continue
                # P_j = (remaining + e_j M_j) / M_j: a whole number in the prior's support.
                duration = (world.remaining[j] + obs.work_done[j] * unit) / unit
                assert duration == round(duration) and pmf.first <= duration <= pmf.last
                if status != "unstarted":
                    started += 1
                    assert duration > obs.work_done[j]
    assert started > 100


def test_shocked_activity_follows_the_replayed_condition(build: Builder) -> None:
    """p = 10, M = 2, e = 9 and a shock F = 1.5 at e = 8: R = 1.5 (P - 8) - 1 > 0, so P >= 9
    and the remaining work is 1.5 P - 13 full-crew days (spec section 5.1)."""
    inst = build([0, 10, 0], [[0], [2], [0]], [[1], [2], []], capacities=(2,))
    base = initial_observation(inst, Schedule(starts=(0, 0, 10)))
    obs = observed(
        base,
        day=12,
        status=("done", "running", "unstarted"),
        work_done=(0.0, 9.0, 0.0),
        start=(0, 0, None),
        finish=(0, None, None),
        assigned=((), (0, 1), ()),
        work_increases=((1, 8.0, 1.5),),
    )
    belief = Belief(obs)
    pmf = duration_pmf(10, PertParams())
    rng = np.random.default_rng(5)
    seen: dict[int, int] = {}
    for _ in range(4000):
        remaining = belief.sample(rng).remaining[1] / 2  # crew-member days -> full-crew days
        p = round((remaining + 13) / 1.5)
        assert remaining == pytest.approx(1.5 * p - 13) and remaining > 0
        seen[p] = seen.get(p, 0) + 1
    assert min(seen) == 9 and max(seen) <= pmf.last
    share = pmf.probs[9 - pmf.first] / math.fsum(pmf.probs[9 - pmf.first :])
    assert abs(seen[9] / 4000 - share) < 0.03
    # With e = 20 no prior duration (at most 16) is unfinished: one crew-member day remains.
    stuck = Belief(observed(obs, work_done=(0.0, 20.0, 0.0), work_increases=()))
    world = stuck.sample(rng)
    assert stuck.fallbacks == world.fallbacks == 1
    assert world.remaining[1] == 1.0


def test_absence_posterior_support_and_moments(build: Builder) -> None:
    q = 1 / 3
    # Absent since day s = 3, today t = 10: at least t - s + 1 = 8 days, or L_low if larger.
    for announced, least in ((2, 8), (12, 12)):
        posterior = absence_posterior(q, max(announced, 10 - 3 + 1))
        assert posterior is not None and posterior.first == least
        assert posterior.last == MAX_ABSENCE
    # L_low = 1 and t = s: the geometric prior times the likelihood 1 / L, truncated at 365.
    posterior = absence_posterior(q, 1)
    assert posterior is not None
    weights = [q * (1 - q) ** (n - 1) / n for n in range(1, MAX_ABSENCE + 1)]
    total = math.fsum(weights)
    assert math.fsum(posterior.probs) == pytest.approx(1.0, abs=1e-12)
    assert posterior.probs == pytest.approx([w / total for w in weights], rel=1e-9)
    mean = math.fsum(n * w for n, w in zip(range(1, MAX_ABSENCE + 1), weights, strict=True))
    assert posterior.mean == pytest.approx(mean / total, rel=1e-12)
    # Untruncated: sum q (1-q)^(L-1) / L = -q ln q / (1 - q), so E[L] = (1 - q) / (-q ln q).
    assert posterior.mean == pytest.approx((1 - q) / (-q * math.log(q)), rel=1e-12)
    assert absence_posterior(q, MAX_ABSENCE + 1) is None
    assert absence_posterior(1.0, 2) is None  # E[L] = 1 allows only L = 1


def test_absent_workers_return_after_today(build: Builder) -> None:
    inst = build([0, 4, 0], [[0], [2], [0]], [[1], [2], []], capacities=(3,))
    base = initial_observation(inst, Schedule(starts=(0, 0, 4)))
    obs = observed(
        base,
        day=10,
        present=(False, False, True),
        absent_since=(3, 10, None),
        announced=(2, 4, None),
    )
    rng = np.random.default_rng(3)
    worlds = [sample_world(obs, rng) for _ in range(500)]
    assert all(w.return_day[2] == -1 for w in worlds)
    assert min(w.return_day[0] for w in worlds) == 3 + 8  # back on s + L, L >= 8
    assert min(w.return_day[1] for w in worlds) == 10 + 4  # L >= L_low = 4
    assert all(w.fallbacks == 0 for w in worlds)
    # The same generator state gives the same world.
    first, second = (sample_world(obs, np.random.default_rng(9)) for _ in range(2))
    assert first == second
