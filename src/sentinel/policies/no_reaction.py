"""NoReaction: keep the plan; paused activities wait for their workers (spec section 7)."""

from typing import ClassVar

from sentinel.policies.base import EMPTY_DECISION, Decision
from sentinel.simulation.state import Observation


class NoReaction:
    """Base policy of the rollouts: never intervenes (spec sections 6-7)."""

    passive: ClassVar[bool] = True

    def decide(self, observation: Observation) -> Decision:
        """Always the empty decision."""
        return EMPTY_DECISION
