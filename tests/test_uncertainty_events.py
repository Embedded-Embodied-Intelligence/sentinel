"""PERT durations, derived deadline and budget, and the disruption streams of spec 2.1-2.3."""

from itertools import pairwise

import numpy as np
import pytest

from sentinel.model import ProjectInstance
from sentinel.simulation.events import DisruptionParams, ScenarioStreams
from sentinel.simulation.uncertainty import (
    PertParams,
    derive_budget,
    derive_deadline,
    expected_durations,
    pert_multipliers,
    realise_durations,
)


def test_pert_sample_mean_and_support() -> None:
    params = PertParams()
    x = pert_multipliers(100_000, np.random.default_rng(7), params)
    assert abs(x.mean() - (params.a + 4 * params.m + params.b) / 6) < 0.005
    assert x.min() >= params.a and x.max() <= params.b


def test_degenerate_pert_is_constant_without_drawing() -> None:
    rng = np.random.default_rng(1)
    state = rng.bit_generator.state
    assert pert_multipliers(5, rng, PertParams(a=1.0, m=1.0, b=1.0)).tolist() == [1.0] * 5
    assert rng.bit_generator.state == state


def test_realised_durations_keep_zero_and_round(tiny: ProjectInstance) -> None:
    rng = np.random.default_rng(0)
    assert realise_durations(tiny, rng, PertParams(a=1.0, m=1.0, b=1.0)) == (0, 3, 2, 4, 0)
    doubled = realise_durations(tiny, rng, PertParams(a=2.0, m=2.0, b=2.0))
    assert doubled == (0, 6, 4, 8, 0)


def test_derive_deadline_and_budget(tiny: ProjectInstance) -> None:
    assert derive_deadline(10, 0.1) == 11  # 1.1 * 10 is 11.000000000000002 in floating point
    assert derive_deadline(43, 0.1) == 48
    mean = PertParams().mean
    assert expected_durations(tiny, PertParams())[1] == pytest.approx(3 * mean)
    # Work r_jk p_j: 2*3 + 2*2 + 1*4 = 14 worker-days at nominal durations.
    assert derive_budget(tiny, 0.1) == pytest.approx(1.1 * 14 * mean)
    assert derive_budget(tiny, 0.0, [2.0]) == pytest.approx(28 * mean)


def test_absences_follow_the_d1_rules(tiny: ProjectInstance) -> None:
    params = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0, lambda_n=0)
    streams = ScenarioStreams(11, tiny, params, PertParams())
    onsets = [(day, a) for day in range(3000) for a in streams.absence_onsets(day)]
    lengths = [a.length for _, a in onsets]
    assert len(onsets) > 100
    assert abs(np.mean(lengths) - 3) < 0.3
    assert all(1 <= a.announced <= a.length for _, a in onsets)
    for w in range(len(tiny.workers)):
        own = [(day, a.length) for day, a in onsets if a.worker == w]
        for (day, length), (next_day, _) in pairwise(own):
            assert next_day >= day + length + 1  # no draw on the return day


def test_streams_do_not_depend_on_query_order(tiny: ProjectInstance) -> None:
    params = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.3, lambda_n=0.2)
    first = ScenarioStreams(5, tiny, params, PertParams())
    second = ScenarioStreams(5, tiny, params, PertParams())
    assert second.absence_onsets(300) == first.absence_onsets(300)
    assert [second.new_activity(d) for d in range(300)] == [
        first.new_activity(d) for d in range(300)
    ]
    assert second.work_shock(1, 40, 80) == first.work_shock(1, 40, 80)
    assert first.durations == second.durations
