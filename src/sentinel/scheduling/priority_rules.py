"""Priority rules for the serial SGS: LFT, LST, MTS and GRPW (as compared in Kolisch 1996).

Every rule returns one priority value per activity id (dummies included). `PRIORITY_RULES`
records whether lower or higher values are preferred; the SGS breaks ties by the smallest id.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sentinel.model.instance import ProjectInstance
from sentinel.scheduling.bounds import latest_finishes, latest_starts

RuleName = Literal["lft", "lst", "mts", "grpw"]


def lft_priorities(instance: ProjectInstance) -> tuple[int, ...]:
    """LFT: latest finish times LF_j for horizon LB0; lower is better (Kolisch 1996)."""
    return latest_finishes(instance)


def lst_priorities(instance: ProjectInstance) -> tuple[int, ...]:
    """LST: latest start times LS_j for horizon LB0; lower is better (Kolisch 1996)."""
    return latest_starts(instance)


def mts_priorities(instance: ProjectInstance) -> tuple[int, ...]:
    """MTS: count of transitive successors (sink included); higher is better (Kolisch 1996)."""
    reach = [0] * instance.n_activities  # bit s of reach[j] is set iff s is a successor of j
    for j in reversed(instance.topological_order()):
        for succ in instance.activities[j].successors:
            reach[j] |= reach[succ] | (1 << succ)
    return tuple(bits.bit_count() for bits in reach)


def grpw_priorities(instance: ProjectInstance) -> tuple[int, ...]:
    """GRPW: p_j plus the durations of the immediate successors; higher is better (Kolisch 1996)."""
    acts = instance.activities
    return tuple(act.duration + sum(acts[s].duration for s in act.successors) for act in acts)


@dataclass(frozen=True)
class PriorityRule:
    """A priority rule: its priority function and whether lower values are preferred."""

    name: RuleName
    priorities: Callable[[ProjectInstance], tuple[int, ...]]
    lower_is_better: bool


PRIORITY_RULES: dict[RuleName, PriorityRule] = {
    "lft": PriorityRule("lft", lft_priorities, lower_is_better=True),
    "lst": PriorityRule("lst", lst_priorities, lower_is_better=True),
    "mts": PriorityRule("mts", mts_priorities, lower_is_better=False),
    "grpw": PriorityRule("grpw", grpw_priorities, lower_is_better=False),
}
