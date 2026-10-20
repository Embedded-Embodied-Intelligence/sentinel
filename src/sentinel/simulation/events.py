"""Disruption events D1-D3 (spec section 2.2) and their common random numbers (section 2.3)."""

import math
from bisect import bisect_left
from collections.abc import Sequence
from typing import Annotated, Literal, NamedTuple, Self

import numpy as np
import numpy.typing as npt
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from sentinel.model.instance import ProjectInstance
from sentinel.simulation.uncertainty import PertParams, pert_multipliers, realise_durations

Rate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

# Days of absences and D3 draws materialised at a time, and uniforms drawn per buffer refill
# for one worker (absences) or one activity (64 work-day checks of D2).
_CHUNK = 128
_ABSENCE_BLOCK = 512
_WORK_BLOCK = 128


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
    """D2: before progress on its `work_day`-th work day, the remaining work of `activity` became
    before * F (spec section 2.2); work is in full-crew days, `work_done` is e_j before the shock.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["work_increase"] = "work_increase"
    day: NonNegativeInt
    activity: NonNegativeInt
    work_day: PositiveInt
    work_done: NonNegativeFloat
    factor: float
    remaining_before: PositiveFloat  # hidden
    remaining_after: PositiveFloat  # hidden


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


class _Uniforms:
    """A growing buffer of one stream's uniforms and the positions of those below `rate`.

    With `step = 2` only even positions are tested (the Bernoulli of a (Bernoulli, factor) pair).
    Blocks continue the same stream, so a value depends only on its position.
    """

    __slots__ = ("hits", "rate", "rng", "step", "values")

    def __init__(self, rng: np.random.Generator, rate: float, step: int = 1) -> None:
        self.rng = rng
        self.rate = rate
        self.step = step
        self.values = _NO_DRAWS
        self.hits: list[int] = []  # increasing positions p (multiples of step), values[p] < rate

    def ensure(self, n: int, block: int) -> None:
        """Draw blocks of `block` uniforms (a multiple of `step`) until n are available."""
        while len(self.values) < n:
            start, step = len(self.values), self.step
            new = self.rng.random(block)
            self.values = np.concatenate((self.values, new)) if start else new
            tested = new if step == 1 else new[::step]
            self.hits.extend(start + step * i for i in np.flatnonzero(tested < self.rate).tolist())


class ScenarioStreams:
    """The child streams of one replication seed (spec section 2.3) and the engine's queries.

    `SeedSequence(seed).spawn(4)` gives the streams of (i) durations, (ii) absences, (iii) work
    increases and (iv) new activities; (ii) and (iii) spawn one child per worker and per
    original activity. An answer depends only on the seed, the instance, the parameters and the
    queried day or work-day counter, never on the order of queries or the project state, so
    exogenous events are identical for every policy (common random numbers). Absences and work
    increases transform one uniform per variate, so their streams are read positionally.
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
        self._absence_streams = [
            _Uniforms(_generator(seq), params.lambda_a) for seq in absence_seq.spawn(n_workers)
        ]
        self._absence_at = [0] * n_workers  # index of the next candidate in the worker's hits
        self._absence_pos = [0] * n_workers  # next unread position of the worker's stream
        self._absence_next = [0] * n_workers  # next day that needs a Bernoulli draw
        self._absence_horizon = 0  # onsets are known for all days before it
        self._onsets: dict[int, list[AbsenceDraw]] = {}
        q = 1 / params.mean_absence
        self._log_no_return = math.log1p(-q) if q < 1 else 0.0

        n_work = instance.n_activities if params.lambda_s > 0 else 0
        self._work_seqs = work_seq.spawn(n_work)
        self._work_streams: list[_Uniforms | None] = [None] * n_work

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
        onsets = self._onsets
        for w, stream in enumerate(self._absence_streams):
            hits = stream.hits
            at, pos, day = self._absence_at[w], self._absence_pos[w], self._absence_next[w]
            while day < end:
                # Bernoullis for days day .. end-1, plus L and L_low of an onset on day end-1.
                stream.ensure(pos + end - day + 2, _ABSENCE_BLOCK)
                while at < len(hits) and hits[at] < pos:
                    at += 1
                if at == len(hits) or hits[at] - pos >= end - day:
                    pos += end - day
                    day = end
                    break
                h = hits[at]
                onset = day + h - pos
                length = self._absence_length(float(stream.values[h + 1]))
                announced = 1 + int(float(stream.values[h + 2]) * length)  # Uniform{1, ..., L}
                onsets.setdefault(onset, []).append(AbsenceDraw(w, length, announced))
                pos = h + 3
                # Absent on days onset .. onset+L-1 and back on onset+L, a day without a draw;
                # draws resume the day after the return (spec section 2.2 D1).
                day = onset + length + 1
            self._absence_at[w], self._absence_pos[w], self._absence_next[w] = at, pos, day
        self._absence_horizon = end

    def _absence_length(self, u: float) -> int:
        """L = 1 + floor(ln(1 - u) / ln(1 - q)), q = 1/E[L]: numpy's geometric(q) on {1, 2, ...}."""
        if self._log_no_return == 0.0:  # E[L] = 1
            return 1
        return 1 + int(math.log1p(-u) / self._log_no_return)

    def work_shock(self, activity: int, first: int, last: int) -> tuple[int, float] | None:
        """First work-day counter k in [first, last] with a D2 shock of `activity`, and its F.

        The check of the k-th work day reads uniforms 2k - 2 (Bernoulli) and 2k - 1 (factor) of
        the activity's stream (spec section 2.3 (iii)).
        """
        if last < first or not self._work_seqs:
            return None
        if activity >= self._n_original:
            # D2 streams exist per original activity only, so activities inserted by D3 never
            # get work increases (spec sections 2.2 D2, 2.3 (iii)).
            return None
        stream = self._work_streams[activity]
        if stream is None:
            rng = _generator(self._work_seqs[activity])
            stream = self._work_streams[activity] = _Uniforms(rng, self.params.lambda_s, step=2)
        # Draw block by block until a hit at or after check `first` appears or the window is
        # covered, so a long window (large remaining work) costs about 1 / lambda_S checks.
        while True:
            i = bisect_left(stream.hits, 2 * first - 2)
            if i < len(stream.hits) or len(stream.values) >= 2 * last:
                break
            stream.ensure(len(stream.values) + _WORK_BLOCK, _WORK_BLOCK)
        if i == len(stream.hits) or stream.hits[i] > 2 * last - 2:
            return None
        h = stream.hits[i]
        f_low, f_high = self.params.f_low, self.params.f_high
        return h // 2 + 1, f_low + (f_high - f_low) * float(stream.values[h + 1])

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
