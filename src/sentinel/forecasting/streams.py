"""Random layout of the disruptions after the observed day in a rollout (spec 5.1, ADR-0009).

The world draws one Bernoulli per worker and day and per activity and work day (spec section
2.3). A rollout instead jumps from event to event: the gap to the next D1 onset, D2 shock or D3
arrival is geometric, which is the distribution of the first success of those Bernoulli
sequences (spec section 2.2), so one draw replaces a run of failures. Draws come in blocks that
cover every worker or activity at once: round r of a block holds the r-th absence of every
worker (gap, L, L_low) and the r-th shock of every original activity (gap, F); D3 blocks hold
the next arrivals (gap, three uniforms, PERT multiplier). The k-th event of a worker or activity
therefore reads the same uniforms whatever is simulated, so the same seed gives the same
state-independent events for every candidate plan.
"""

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from sentinel.simulation.events import AbsenceDraw, DisruptionParams, NewActivityDraw
from sentinel.simulation.uncertainty import PertParams, pert_multipliers

ROUNDS = 4  # absences per worker, or D2 shocks per activity, drawn per block
ARRIVALS = 8  # D3 arrivals drawn per block
CHUNK = 32  # days of absence onsets materialised at a time

IntArray = npt.NDArray[np.int64]


def geometric(u: npt.NDArray[np.float64], p: float) -> IntArray:
    """Geometric(p) on {1, 2, ...} by inversion, 1 + floor(ln(1 - u) / ln(1 - p)) as in the
    world's absence lengths; p = 1 gives 1. Values are capped at 2^40, far beyond any horizon."""
    if p >= 1:
        return np.ones(u.shape, dtype=np.int64)
    ratio = np.log1p(-u) / math.log1p(-p)
    return (1 + np.minimum(np.floor(ratio), 2.0**40)).astype(np.int64)


class RolloutStreams:
    """D1-D3 after day `day` of one rollout, with the distributions of spec section 2.2.

    `return_day` gives each worker's return from a current absence (-1 if present): draws for a
    worker resume the day after its return (spec section 2.2 D1), for a present one on day
    `day + 1`. D2 counts work days from the start of the rollout and applies to original
    activities only; D3 arrivals start on day `day + 1`. `seq` spawns one child stream per
    process. Answers depend only on `seq`, the parameters and the query, never on query order;
    the D2 queries of one activity only move forward within a rollout, so streams shared by
    several rollouts from the same day (candidates in one sampled world) are `rewind`-ed first.
    """

    __slots__ = (
        "_abs_announced",
        "_abs_horizon",
        "_abs_length",
        "_abs_next",
        "_abs_rng",
        "_abs_round",
        "_abs_values",
        "_log_no_return",
        "_new",
        "_new_last",
        "_new_rng",
        "_onsets",
        "_work_cursor",
        "_work_factor",
        "_work_pos",
        "_work_rng",
        "n_original",
        "params",
        "pert",
    )

    def __init__(
        self,
        seq: np.random.SeedSequence,
        params: DisruptionParams,
        pert: PertParams,
        *,
        day: int,
        n_original: int,
        return_day: Sequence[int],
    ) -> None:
        self.params = params
        self.pert = pert
        self.n_original = n_original
        absence_seq, work_seq, new_seq = seq.spawn(3)
        self._onsets: dict[int, list[AbsenceDraw]] = {}
        self._abs_horizon = day + 1  # onsets are known for all days before it
        q = 1 / params.mean_absence
        self._log_no_return = math.log1p(-q) if q < 1 else 0.0
        if params.lambda_a > 0 and return_day:
            self._abs_rng: np.random.Generator | None = _generator(absence_seq)
            self._abs_values = self._abs_rng.random((ROUNDS, len(return_day), 3))
            first = np.array([day + 1 if r < 0 else r + 1 for r in return_day], dtype=np.int64)
            self._abs_round = np.zeros(len(return_day), dtype=np.int64)
            self._abs_next, self._abs_length, self._abs_announced = self._absence(
                first, self._abs_values[0]
            )
        else:
            self._abs_rng = None
        self._work_rng = _generator(work_seq) if params.lambda_s > 0 and n_original else None
        self._work_pos: list[list[int]] = [[] for _ in range(n_original)]
        self._work_factor: list[list[float]] = [[] for _ in range(n_original)]
        self._work_cursor = [0] * n_original
        self._new_rng = _generator(new_seq) if params.lambda_n > 0 else None
        self._new: dict[int, NewActivityDraw] = {}
        self._new_last = day  # day of the last arrival drawn so far

    def rewind(self) -> None:
        """Start the D2 queries of a new rollout from the same day; drawn values are kept."""
        self._work_cursor = [0] * self.n_original

    def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
        """Absences that start on `day`, by increasing worker id (spec section 2.2 D1)."""
        if self._abs_rng is None:
            return ()
        while day >= self._abs_horizon:
            self._extend_absences()
        return self._onsets.get(day, ())

    def _absence(
        self, first: IntArray, u: npt.NDArray[np.float64]
    ) -> tuple[IntArray, IntArray, IntArray]:
        """Onset day, L and L_low of an absence from the uniforms (gap, L, L_low) of its round,
        for workers whose draws resume on day `first`."""
        onset = first + geometric(u[:, 0], self.params.lambda_a) - 1
        if self._log_no_return == 0.0:  # E[L] = 1
            length = np.ones(len(first), dtype=np.int64)
        else:
            ratio = np.log1p(-u[:, 1]) / self._log_no_return
            length = (1 + np.minimum(np.floor(ratio), 2.0**40)).astype(np.int64)
        announced = (1 + np.floor(u[:, 2] * length)).astype(np.int64)  # Uniform{1, ..., L}
        return onset, length, announced

    def _extend_absences(self) -> None:
        """Materialise the onsets of the next CHUNK days for all workers."""
        assert self._abs_rng is not None
        end = self._abs_horizon + CHUNK
        days: set[int] = set()
        while True:
            due = np.flatnonzero(self._abs_next < end)
            if not due.size:
                break
            onsets = zip(
                due.tolist(),
                self._abs_next[due].tolist(),
                self._abs_length[due].tolist(),
                self._abs_announced[due].tolist(),
                strict=True,
            )
            for w, onset, length, announced in onsets:
                self._onsets.setdefault(onset, []).append(AbsenceDraw(w, length, announced))
                days.add(onset)
            # Back on onset + L without a draw; draws resume the day after (spec section 2.2 D1).
            first = self._abs_next[due] + self._abs_length[due] + 1
            rounds = self._abs_round[due] + 1
            self._abs_round[due] = rounds
            while rounds.max() >= len(self._abs_values):
                block = self._abs_rng.random((ROUNDS, self._abs_values.shape[1], 3))
                self._abs_values = np.concatenate((self._abs_values, block))
            onset, length, announced = self._absence(first, self._abs_values[rounds, due])
            self._abs_next[due], self._abs_length[due], self._abs_announced[due] = (
                onset,
                length,
                announced,
            )
        for d in days:  # several rounds can add onsets to one day
            self._onsets[d].sort()
        self._abs_horizon = end

    def work_shock(self, activity: int, first: int, last: int) -> tuple[int, float] | None:
        """First work-day counter k in [first, last] with a D2 shock of `activity`, and its F.

        Shocks of an original activity sit at the partial sums of geometric(lambda_S) gaps; the
        counter starts at the beginning of the rollout. Queries of one activity never go back.
        """
        if self._work_rng is None or activity >= self.n_original or last < first:
            return None
        positions, factors = self._work_pos[activity], self._work_factor[activity]
        r = self._work_cursor[activity]
        while True:
            while r >= len(positions):
                self._extend_shocks()
            if positions[r] >= first:
                break
            r += 1
        self._work_cursor[activity] = r
        if positions[r] > last:
            return None
        return positions[r], factors[r]

    def _extend_shocks(self) -> None:
        """Draw the next ROUNDS shocks (gap, F) of every original activity."""
        assert self._work_rng is not None
        u = self._work_rng.random((ROUNDS, self.n_original, 2))
        gaps = geometric(u[:, :, 0], self.params.lambda_s)
        f_low, f_high = self.params.f_low, self.params.f_high
        factors = (f_low + (f_high - f_low) * u[:, :, 1]).T.tolist()
        for j, (steps, fs) in enumerate(zip(gaps.T.tolist(), factors, strict=True)):
            positions = self._work_pos[j]
            k = positions[-1] if positions else 0
            for step in steps:
                k += step
                positions.append(k)
            self._work_factor[j].extend(fs)

    def new_activity(self, day: int) -> NewActivityDraw | None:
        """The D3 draws of `day` if a new activity arrives that day (spec section 2.2 D3)."""
        if self._new_rng is None:
            return None
        while self._new_last < day:
            self._extend_arrivals(self._new_rng)
        return self._new.get(day)

    def _extend_arrivals(self, rng: np.random.Generator) -> None:
        """The next ARRIVALS arrivals: four uniforms each (gap, template, successor,
        predecessor), then one PERT multiplier each."""
        u = rng.random((ARRIVALS, 4))
        multipliers = pert_multipliers(ARRIVALS, rng, self.pert).tolist()
        day = self._new_last
        for gap, (_, template, successor, predecessor), multiplier in zip(
            geometric(u[:, 0], self.params.lambda_n).tolist(), u.tolist(), multipliers, strict=True
        ):
            day += gap
            self._new[day] = NewActivityDraw(template, multiplier, successor, predecessor)
        self._new_last = day


def _generator(seq: np.random.SeedSequence) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seq))
