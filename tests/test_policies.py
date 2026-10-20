"""Policy interface and the NoReaction base policy."""

import pytest
from pydantic import ValidationError

from sentinel.model import ProjectInstance
from sentinel.policies.base import EMPTY_DECISION, Decision, Noop
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import PertParams


class NoopPolicy:
    """Test-only policy that always sends an explicit NOOP operation."""

    def __init__(self) -> None:
        self.calls = 0

    def decide(self, observation: Observation) -> Decision:
        self.calls += 1
        return Decision(operations=(Noop(),))


def test_decisions_accept_only_known_operations() -> None:
    assert Decision().operations == ()
    assert Decision.model_validate({"operations": [{"kind": "noop"}]}).operations == (Noop(),)
    with pytest.raises(ValidationError):
        Decision.model_validate({"operations": [{"kind": "subst"}]})


def test_no_reaction_never_intervenes(tiny: ProjectInstance) -> None:
    assert NoReaction.passive is True
    plan = serial_sgs(tiny, lft_priorities(tiny), lower_is_better=True)
    params = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1)
    noop = NoopPolicy()
    for seed in range(5):
        base = simulate(tiny, plan, NoReaction(), seed, pert=PertParams(), disruptions=params)
        same = simulate(tiny, plan, noop, seed, pert=PertParams(), disruptions=params)
        assert same == base  # NOOP changes nothing, and skipping the passive policy neither
    assert noop.calls > 0


def test_no_reaction_returns_the_empty_decision(tiny: ProjectInstance) -> None:
    observations: list[Observation] = []

    class Spy:
        def decide(self, observation: Observation) -> Decision:
            observations.append(observation)
            return EMPTY_DECISION

    plan = serial_sgs(tiny, lft_priorities(tiny), lower_is_better=True)
    simulate(tiny, plan, Spy(), 0, pert=PertParams(), disruptions=DisruptionParams.none())
    assert observations
    assert all(NoReaction().decide(obs) is EMPTY_DECISION for obs in observations)
