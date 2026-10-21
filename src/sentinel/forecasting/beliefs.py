"""Belief over the hidden state given an observation, and samples from it (spec section 5.1)."""

import math
from typing import NamedTuple

import numpy as np

from sentinel.forecasting.durations import IntegerPmf, duration_pmf
from sentinel.simulation.state import (
    DONE,
    UNSTARTED,
    Observation,
    SampledWorld,
    crew_member_days,
    work_history,
)

MAX_ABSENCE = 365  # the absence posterior is truncated at L <= 365 days (spec section 5.1)
# Remaining work at or below this many crew-member days means the activity would have finished.
FINISHED = 1e-9


class _Duration(NamedTuple):
    """Sampler of one hidden duration: P_j from `pmf`, remaining work `table[P_j - pmf.first]`."""

    activity: int
    pmf: IntegerPmf
    table: tuple[float, ...]


class _Return(NamedTuple):
    """Sampler of one absent worker's return day `start + L`, L from `pmf`."""

    worker: int
    start: int
    pmf: IntegerPmf


class Belief:
    """The posterior of the hidden quantities given one observation (spec section 5.1).

    Built once per observation and sampled many times. Work is counted in crew-member days as in
    the engine (M_j per full-crew day). A sample takes one uniform per activity and per worker in
    a single draw (activity j reads uniform j, worker w uniform n + w), so a generator gives the
    same world whatever is simulated from it afterwards. Conditions with probability zero under
    the prior (possible after large D2 shocks) fall back to the smallest feasible value and are
    counted in `fallbacks`; they depend on the observation only, so every sample has the same.
    SUBST handovers enter the replay of the observed work like D2 shocks (`_remaining`).
    """

    __slots__ = ("_durations", "_fixed", "_returns", "fallbacks", "n_activities", "n_workers")

    def __init__(self, observation: Observation) -> None:
        instance, pert = observation.instance, observation.pert
        n_original = instance.n_activities
        self.n_activities = n = len(observation.status)
        self.n_workers = len(observation.present)
        self.fallbacks = 0
        changes = work_history(observation)
        self._fixed = [0.0] * n  # remaining work of finished activities and of fallbacks
        self._durations: list[_Duration] = []
        for j, status in enumerate(observation.status):
            if status == DONE:
                continue
            if j < n_original:
                act = instance.activities[j]
                nominal, demands = act.duration, act.demands
            else:
                inserted = observation.inserted[j - n_original]
                nominal, demands = inserted.duration, inserted.demands
            unit = max(1, sum(demands))  # M_j crew-member days per full-crew day
            pmf = duration_pmf(nominal, pert)
            if status == UNSTARTED:
                table = tuple(float(p * unit) for p in range(pmf.first, pmf.last + 1))
                self._durations.append(_Duration(j, pmf, table))
                continue
            done = crew_member_days(observation.work_done[j], unit)
            history = changes.get(j, [])
            values = range(pmf.first, pmf.last + 1)
            remaining = [_remaining(p * unit, done, history) for p in values]
            # Remaining work grows with P_j, so the feasible values are a top range of the pmf.
            feasible = [r > FINISHED for r in remaining]
            least = pmf.first + feasible.index(True) if True in feasible else None
            conditional = None if least is None else pmf.at_least(least)
            if conditional is None:
                self.fallbacks += 1
                self._fixed[j] = 1.0  # one crew-member day, i.e. 1 / M_j full-crew days
                continue
            table = tuple(remaining[conditional.first - pmf.first :])
            self._durations.append(_Duration(j, conditional, table))
        self._returns: list[_Return] = []
        q = 1 / observation.disruptions.mean_absence
        for w in range(len(instance.workers)):  # temporary workers are never absent
            if observation.present[w]:
                continue
            start, announced = observation.absent_since[w], observation.announced[w]
            if start is None or announced is None:
                raise ValueError(f"absent worker {w} has no absence start or announced bound")
            least = max(announced, observation.day - start + 1)
            posterior = absence_posterior(q, least)
            if posterior is None:
                self.fallbacks += 1
                posterior = IntegerPmf(least, (1.0,))
            self._returns.append(_Return(w, start, posterior))

    def sample(self, rng: np.random.Generator) -> SampledWorld:
        """One world: remaining work of every activity and the return day of every worker."""
        uniforms = rng.random(self.n_activities + self.n_workers).tolist()
        remaining = self._fixed.copy()
        for j, pmf, table in self._durations:
            remaining[j] = table[pmf.sample(uniforms[j]) - pmf.first]
        return_day = [-1] * self.n_workers
        n = self.n_activities
        for w, start, pmf in self._returns:
            return_day[w] = start + pmf.sample(uniforms[n + w])
        return SampledWorld(tuple(remaining), tuple(return_day), self.fallbacks)

    def expected_remaining(self) -> tuple[float, ...]:
        """E[remaining work] of every activity under the belief, in crew-member days."""
        expected = self._fixed.copy()
        for j, pmf, table in self._durations:
            expected[j] = math.fsum(p * r for p, r in zip(pmf.probs, table, strict=True))
        return tuple(expected)


def sample_world(observation: Observation, rng: np.random.Generator) -> SampledWorld:
    """One sample of the hidden state given `observation` (spec section 5.1)."""
    return Belief(observation).sample(rng)


def absence_posterior(q: float, least: int) -> IntegerPmf | None:
    """Posterior of the absence length L given L >= `least` (spec section 5.1).

    Geometric prior q (1 - q)^(L - 1) on {1, 2, ...} with q = 1 / E[L], times the likelihood 1 / L
    of the announced bound L_low ~ Uniform{1, ..., L}, truncated at L <= MAX_ABSENCE; None if no
    length in [least, MAX_ABSENCE] has positive probability.
    """
    if least > MAX_ABSENCE:
        return None
    lengths = np.arange(least, MAX_ABSENCE + 1)
    weights = (1 - q) ** (lengths - 1) / lengths
    if not weights.sum() > 0:
        return None
    return IntegerPmf(least, weights.tolist())


def _remaining(units: float, done: int, history: list[tuple[int, float, float]]) -> float:
    """R_m - (e_j - e_m) of spec section 5.1 in crew-member days: start from P_j M_j and replay
    the work done between the observed changes (work done, factor, work added; `work_history`).

    A D2 shock multiplies the remaining work by F, a SUBST handover adds h_j M_j. The activity
    must not have finished before a handover, else the value is -inf (infeasible); before a
    shock that follows from the final condition, since every F >= 1.
    """
    before = 0
    for work_done, factor, added in history:
        units -= work_done - before
        if added:
            if units <= FINISHED:
                return -math.inf
            units += added
        else:
            units *= factor
        before = work_done
    return units - (done - before)
