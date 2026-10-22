"""Policy interface: at each decision epoch a policy maps an observation to a decision."""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

from sentinel.simulation.state import Observation


class Noop(BaseModel):
    """NOOP: keep the plan and the assignments unchanged (spec section 4, level 0)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["noop"] = "noop"


class Subst(BaseModel):
    """SUBST(j, W'): the idle present `workers` W' replace absent crew members of the paused or
    running `activity` j, one member of the same role each (spec section 4, level 2).

    Within a role, the substitutes in the order given replace the absent members in increasing
    id order; the handover cost h_j counts m_j = |W'| (spec section 3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["subst"] = "subst"
    activity: NonNegativeInt
    workers: tuple[NonNegativeInt, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_distinct(self) -> Self:
        if len(set(self.workers)) != len(self.workers):
            raise ValueError(f"substitutes must be distinct, got {self.workers}")
        return self


class Reseq(BaseModel):
    """RESEQ(pi'): new planned starts of all unstarted activities, by activity id; they must be
    a feasible solution of the residual problem (spec sections 4 and 4.1, level 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["reseq"] = "reseq"
    starts: dict[NonNegativeInt, NonNegativeInt]


class Shift(BaseModel):
    """SHIFT(pi'): the order-preserving repair (spec section 4, level 0). New planned starts of
    all unstarted activities, by activity id: a feasible solution of the residual problem whose
    starts keep the order of the current plan (`sentinel.scheduling.residual.validate_shift`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["shift"] = "shift"
    starts: dict[NonNegativeInt, NonNegativeInt]


class Overtime(BaseModel):
    """OVERTIME(k, u, H): hire `workers` = u temporary workers of `role` k for the `days` = H days
    from today (spec section 4, level 2); at most floor(gamma R_k) of a role are hired at once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["overtime"] = "overtime"
    role: NonNegativeInt
    workers: PositiveInt
    days: PositiveInt


class Descope(BaseModel):
    """DESCOPE(j): remove the unstarted optional `activity` j, whose only successor is the sink
    (spec section 4, level 2; it always needs approval)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["descope"] = "descope"
    activity: NonNegativeInt


Operation = Annotated[
    Noop | Shift | Reseq | Subst | Overtime | Descope, Field(discriminator="kind")
]

# Permission level of each operation (spec section 4): 0 automatic, 1 automatic with report,
# 2 human approval; DESCOPE always needs approval, whatever the autonomy level.
LEVELS: dict[str, int] = {
    "noop": 0,
    "shift": 0,
    "reseq": 1,
    "subst": 2,
    "overtime": 2,
    "descope": 2,
}


class Decision(BaseModel):
    """Operations to apply at step 3 of the day (spec section 3); empty means no change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operations: tuple[Operation, ...] = ()

    @property
    def level(self) -> int:
        """l(a): the maximum permission level of the operations, 0 without any (spec 4)."""
        return max((LEVELS[op.kind] for op in self.operations), default=0)

    @property
    def descopes(self) -> bool:
        """Whether the decision removes an activity (DESCOPE always needs approval, spec 4)."""
        return any(op.kind == "descope" for op in self.operations)


EMPTY_DECISION = Decision()


@dataclass
class DecisionStats:
    """What a reactive policy did in one run: its decisions, the time spent in `decide`, and
    for re-solving policies the RESEQ plans computed, the CP-SAT stages that fell back (spec
    section 7) and the solver's effort."""

    decisions: int = 0
    decide_time_s: float = 0.0
    reseqs: int = 0
    fallbacks: int = 0
    solve_time_s: float = 0.0
    deterministic_time: float = 0.0


class Policy(Protocol):
    """Anything that can decide at a decision epoch from what the agent may observe.

    A policy class may set `passive = True` to promise that it always returns the empty
    decision; the engine then counts its decision epochs without building observations, which
    leaves results unchanged and keeps rollouts on the base policy fast. A policy may also set
    an attribute `requested_epoch` in `decide`, a later day or None: the engine makes that day a
    decision epoch (spec section 3.1 g, the approval day of an escalated action).
    """

    def decide(self, observation: Observation) -> Decision:
        """The decision for the observed state."""
        ...
