"""Sentinel's decision rule (spec section 6) and the record of every decision.

Lexicographic rule: among the candidates racing kept, those whose capped on-time estimate
min(p, theta_D) is within `se_factor` paired standard errors of the best are tied; among them
the smallest budget overrun o wins, then the smallest instability Delta, then the lowest
permission level l, then the larger capped estimate and finally the earlier candidate. The
scalarised ablation maximises U_a = p_a - lambda_B o_a - lambda_Delta Delta_a, then prefers the
lower level and the earlier candidate. A `DecisionRecord` keeps what an explanation (WP6) or
the dashboard (WP8) needs: the epoch, the needs, every candidate with its statistics, the
choice and the reason.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.agent.evaluate import CandidateStats
from sentinel.agent.params import SentinelParams
from sentinel.policies.base import Decision

# Why a decision was taken: no deliberation (only idle workers' events), the needs gate, a
# single valid candidate, the component of the lexicographic rule that separated the choice
# from the runner-up among the tied candidates, or the scalarised utility.
Reason = Literal[
    "idle_events",
    "needs_met",
    "only_candidate",
    "on_time",
    "budget",
    "stability",
    "level",
    "order",
    "utility",
]


class Choice(BaseModel):
    """The chosen candidate (index into the statistics), the reason and the indices tied with
    the best on the capped on-time estimate (lexicographic rule)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: NonNegativeInt
    reason: Reason
    ties: tuple[NonNegativeInt, ...]


def choose(stats: Sequence[CandidateStats], params: SentinelParams) -> Choice:
    """The candidate of the decision rule of `params` (spec section 6) among those not dropped."""
    survivors = [a for a, s in enumerate(stats) if not s.dropped]
    if not survivors:
        raise ValueError("no candidate to choose from")
    if params.rule == "scalarised":
        index = max(survivors, key=lambda a: (stats[a].utility, -stats[a].level, -a))
        return Choice(index=index, reason="utility", ties=(index,))
    top = max(survivors, key=lambda a: (stats[a].capped, -a))
    best = stats[top].capped
    ties = [
        a
        for a in survivors
        if best - stats[a].capped <= params.se_factor * stats[a].se_vs_best or a == top
    ]

    def key(a: int) -> tuple[float, float, int, float, int]:
        s = stats[a]
        return (-s.overrun, -s.deviation, -s.level, s.capped, -a)

    ranked = sorted(ties, key=key, reverse=True)
    reason: Reason = "on_time"
    if len(ranked) > 1:
        names: tuple[Reason, ...] = ("budget", "stability", "level", "on_time", "order")
        first, second = key(ranked[0]), key(ranked[1])
        reason = next(name for name, x, y in zip(names, first, second, strict=True) if x != y)
    return Choice(index=ranked[0], reason=reason, ties=tuple(sorted(ties)))


class Needs(BaseModel):
    """The needs of NOOP (spec section 5): n_D = max(0, theta_D - p_NOOP) and n_B = o_NOOP
    from `rollouts` rollouts, and whether both are within epsilon_D and epsilon_B."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deadline: NonNegativeFloat
    budget: NonNegativeFloat
    p_on_time: NonNegativeFloat
    rollouts: NonNegativeInt
    met: bool


class CandidateRecord(CandidateStats):
    """A candidate's statistics with its operations."""

    decision: Decision


class DecisionRecord(BaseModel):
    """One decision of Sentinel: the `day`, whether it deliberated, the NOOP `needs`, every
    candidate with its statistics (in candidate order), the `chosen` label and decision, the
    `reason`, the candidates `tied` on the deadline component, the rule, the rollouts and
    CP-SAT searches run, and the wall time of generating, evaluating and deciding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    deliberated: bool
    rule: Literal["lexicographic", "scalarised"]
    reason: Reason
    chosen: str
    decision: Decision
    needs: Needs | None = None
    candidates: tuple[CandidateRecord, ...] = ()
    tied: tuple[str, ...] = ()
    rollouts: NonNegativeInt = 0
    cp_solves: NonNegativeInt = 0
    cp_fallbacks: NonNegativeInt = 0
    generation_s: NonNegativeFloat = 0.0
    evaluation_s: NonNegativeFloat = 0.0
    wall_time_s: NonNegativeFloat = 0.0
