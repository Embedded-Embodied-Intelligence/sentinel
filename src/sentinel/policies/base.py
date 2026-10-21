"""Policy interface: at each decision epoch a policy maps an observation to a decision."""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator

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


Operation = Annotated[Noop | Subst | Reseq, Field(discriminator="kind")]


class Decision(BaseModel):
    """Operations to apply at step 3 of the day (spec section 3); empty means no change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operations: tuple[Operation, ...] = ()


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
    leaves results unchanged and keeps rollouts on the base policy fast.
    """

    def decide(self, observation: Observation) -> Decision:
        """The decision for the observed state."""
        ...
