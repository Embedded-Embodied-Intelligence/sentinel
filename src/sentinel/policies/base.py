"""Policy interface: at each decision epoch a policy maps an observation to a decision."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from sentinel.simulation.state import Observation


class Noop(BaseModel):
    """NOOP: keep the plan and the assignments unchanged (spec section 4, level 0)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["noop"] = "noop"


# Extension point: WP4 adds the other operations of spec section 4 as members of this
# discriminated union, e.g. Annotated[Noop | Subst | Reseq, Field(discriminator="kind")].
Operation = Annotated[Noop, Field(discriminator="kind")]


class Decision(BaseModel):
    """Operations to apply at step 3 of the day (spec section 3); empty means no change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operations: tuple[Operation, ...] = ()


EMPTY_DECISION = Decision()


class Policy(Protocol):
    """Anything that can decide at a decision epoch from what the agent may observe.

    A policy class may set `passive = True` to promise that it always returns the empty
    decision; the engine then counts its decision epochs without building observations, which
    leaves results unchanged and keeps rollouts on the base policy fast.
    """

    def decide(self, observation: Observation) -> Decision:
        """The decision for the observed state."""
        ...
