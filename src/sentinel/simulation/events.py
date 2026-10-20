"""Disruption events D1-D3 (spec section 2.2) and their common random numbers (section 2.3)."""

import math
from collections.abc import Sequence
from typing import Annotated, Literal, NamedTuple, Self

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

from sentinel.model.instance import ProjectInstance
from sentinel.simulation.uncertainty import PertParams, pert_multipliers, realise_durations

Rate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

# Days of absences and D3 draws materialised at a time, and spare uniforms per buffer refill.
_CHUNK = 128
_SLACK = 16


class DisruptionParams(BaseModel):
    """Rates of D1 absences, D2 work increases and D3 new activities (spec sections 2.2, 8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lambda_a: Rate  # D1: probability per present worker and day
    mean_absence: float = Field(ge=1, allow_inf_nan=False)  # E[L] in days
    lambda_s: Rate  # D2: probability per running activity and work-day
    f_low: float = Field(default=1.2, ge=1, allow_inf_nan=False)
    f_high: float = Field(default=2.0, ge=1, allow_inf_nan=False)
    lambda_n: Rate  # D3: probability per day

    @model_validator(mode="after")
    def _check_factors(self) -> Self:
        if self.f_low > self.f_high:
            raise ValueError(f"need f_low <= f_high, got {self.f_low} > {self.f_high}")
        return self

    @classmethod
    def none(cls) -> Self:
        """All disruptions disabled; durations stay stochastic (spec section 2.1)."""
        return cls(lambda_a=0.0, mean_absence=1.0, lambda_s=0.0, lambda_n=0.0)


class Absence(BaseModel):
    """D1: `worker` is absent on days `day .. day + length - 1`; `length` is hidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["absence"] = "absence"
    day: NonNegativeInt
    worker: NonNegativeInt
    length: PositiveInt
    announced: PositiveInt  # lower bound L_low told to the agent


class WorkIncrease(BaseModel):
    """D2: after `work_done` work-days the remaining work of `activity` became ceil(before * F)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["work_increase"] = "work_increase"
    day: NonNegativeInt
    activity: NonNegativeInt
    work_done: PositiveInt
    factor: float
    remaining_before: PositiveInt  # hidden
    remaining_after: PositiveInt  # hidden


class NewActivity(BaseModel):
    """D3: `activity` inserted as `predecessor -> activity -> successor`; true duration hidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["new_activity"] = "new_activity"
    day: NonNegativeInt
    activity: NonNegativeInt
    template: PositiveInt
    duration: NonNegativeInt
    true_duration: NonNegativeInt
    demands: tuple[NonNegativeInt, ...]
    predecessor: NonNegativeInt
    successor: NonNegativeInt


class NewActivitySkipped(BaseModel):
    """D3 occurrence that could not be inserted; logged only, not a decision epoch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["new_activity_skipped"] = "new_activity_skipped"
    day: NonNegativeInt
    reason: str


Event = Annotated[
    Absence | WorkIncrease | NewActivity | NewActivitySkipped, Field(discriminator="kind")
]


class AbsenceDraw(NamedTuple):
    """Onset of an absence: the worker, the true length L and the announced bound L_low."""

    worker: int
    length: int
    announced: int


class NewActivityDraw(NamedTuple):
    """Draws of a day on which a D3 activity arrives (spec section 2.3 (iv))."""

    template: float  # uniform mapped onto the real original activities
    multiplier: float  # PERT multiplier of the true duration
    successor: float  # uniform mapped onto the successor candidates
    predecessor: float  # uniform mapped onto the predecessor candidates


def _generator(seq: np.random.SeedSequence) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seq))


_NO_DRAWS: npt.NDArray[np.float64] = np.empty(0)


class ScenarioStreams:
    """The child streams of one replication seed (spec section 2.3) and the engine's queries.

    `SeedSequence(seed).spawn(4)` gives the streams of (i) durations, (ii) absences, (iii) work
    increases and (iv) new activities; (ii) and (iii) spawn one child per worker and per
    original activity. An answer depends only on the seed, the instance, the parameters and the
    queried day or work-day counter, never on the order of queries or the project state, so
    exogenous events are identical for every policy (common random numbers). Absences and work
    increases transform one uniform per variate, so their streams are read positionally from
    buffers that are refilled as needed.
    """

    def __init__(
        self, seed: int, instance: ProjectInstance, params: DisruptionParams, pert: PertParams
    ) -> None:
        durations_seq, absence_seq, work_seq, new_seq = np.random.SeedSequence(seed).spawn(4)
        self.params = params
        self.pert = pert
        self.durations = realise_durations(instance, _generator(durations_seq), pert)
        self._n_original = instance.n_activities

        n_workers = len(instance.workers) if params.lambda_a > 0 else 0
        self._absence_rngs = [_generator(seq) for seq in absence_seq.spawn(n_workers)]
        self._absence_buffers = [_NO_DRAWS] * n_workers
        self._absence_pos = [0] * n_workers  # next unread uniform of each worker's stream
        self._absence_next = [0] * n_workers  # next day that needs a Bernoulli draw
        self._absence_horizon = 0  # onsets are known for all days before it
        self._onsets: dict[int, list[AbsenceDraw]] = {}
        q = 1 / params.mean_absence
        self._log_no_return = math.log1p(-q) if q < 1 else 0.0

        n_work = instance.n_activities if params.lambda_s > 0 else 0
        self._work_seqs = work_seq.spawn(n_work)
        self._work_rngs: list[np.random.Generator | None] = [None] * n_work
        self._work_draws = [_NO_DRAWS] * n_work

        self._new_rng = _generator(new_seq) if params.lambda_n > 0 else None
        self._new_chunks: list[dict[int, NewActivityDraw]] = []

    def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
        """Absences that start on `day`, by increasing worker id (spec section 2.2 D1)."""
        while day >= self._absence_horizon:
            self._extend_absences()
        return self._onsets.get(day, ())

    def _extend_absences(self) -> None:
        """Walk every worker's stream over the next chunk of days (one Bernoulli per day)."""
        end = self._absence_horizon + _CHUNK
        rate = self.params.lambda_a
        for w, rng in enumerate(self._absence_rngs):
            buffer, pos, day = self._absence_buffers[w], self._absence_pos[w], self._absence_next[w]
            while day < end:
                span = end - day
                if pos + span + 2 > len(buffer):  # room for the Bernoullis, L and L_low
                    buffer = np.concatenate((buffer[pos:], rng.random(span + 2 + _SLACK)))
                    pos = 0
                hits = np.flatnonzero(buffer[pos : pos + span] < rate)
                if hits.size == 0:
                    pos += span
                    day = end
                    break
                i = int(hits[0])
                onset = day + i
                length = self._absence_length(float(buffer[pos + i + 1]))
                announced = 1 + int(float(buffer[pos + i + 2]) * length)  # Uniform{1, ..., L}
                pos += i + 3
                self._onsets.setdefault(onset, []).append(AbsenceDraw(w, length, announced))
                # SPEC-Q: absent on days onset .. onset+L-1, back on onset+L without a draw on
                # that day; draws resume the day after the return (spec section 2.2 D1).
                day = onset + length + 1
            self._absence_buffers[w], self._absence_pos[w], self._absence_next[w] = (
                buffer,
                pos,
                day,
            )
        self._absence_horizon = end

    def _absence_length(self, u: float) -> int:
        """L = 1 + floor(ln(1 - u) / ln(1 - q)), q = 1/E[L]: numpy's geometric(q) on {1, 2, ...}."""
        if self._log_no_return == 0.0:  # E[L] = 1
            return 1
        return 1 + int(math.log1p(-u) / self._log_no_return)

    def work_shock(self, activity: int, first: int, last: int) -> tuple[int, float] | None:
        """First work-day counter k in [first, last] with a D2 shock of `activity`, and its F.

        Check k of an activity reads uniforms 2k - 2 (Bernoulli) and 2k - 1 (factor) of the
        activity's stream (spec section 2.3 (iii)).
        """
        if last < first or not self._work_seqs:
            return None
        if activity >= self._n_original:
            # SPEC-Q: D2 streams exist per original activity only (spec section 2.3 (iii)), so
            # activities inserted by D3 never get work increases.
            return None
        draws = self._work_draws[activity]
        if len(draws) < 2 * last:
            rng = self._work_rngs[activity]
            if rng is None:
                rng = self._work_rngs[activity] = _generator(self._work_seqs[activity])
            extra = max(2 * last - len(draws), 2 * _SLACK)
            draws = self._work_draws[activity] = np.concatenate((draws, rng.random(extra)))
        hits = np.flatnonzero(draws[2 * first - 2 : 2 * last : 2] < self.params.lambda_s)
        if hits.size == 0:
            return None
        k = first + int(hits[0])
        f_low, f_high = self.params.f_low, self.params.f_high
        return k, f_low + (f_high - f_low) * float(draws[2 * k - 1])

    def new_activity(self, day: int) -> NewActivityDraw | None:
        """The D3 draws of `day` if a new activity arrives that day (spec section 2.3 (iv))."""
        if self._new_rng is None:
            return None
        chunk, offset = divmod(day, _CHUNK)
        while chunk >= len(self._new_chunks):
            self._new_chunks.append(self._draw_new_chunk(self._new_rng))
        return self._new_chunks[chunk].get(offset)

    def _draw_new_chunk(self, rng: np.random.Generator) -> dict[int, NewActivityDraw]:
        """One chunk of days: four uniforms per day, then one PERT multiplier per day."""
        uniforms = rng.random((_CHUNK, 4))  # occurrence, template, successor, predecessor
        multipliers = pert_multipliers(_CHUNK, rng, self.pert)
        return {
            int(d): NewActivityDraw(
                float(uniforms[d, 1]),
                float(multipliers[d]),
                float(uniforms[d, 2]),
                float(uniforms[d, 3]),
            )
            for d in np.flatnonzero(uniforms[:, 0] < self.params.lambda_n)
        }
