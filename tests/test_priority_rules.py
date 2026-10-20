"""Priority rules LFT, LST, MTS and GRPW."""

from collections.abc import Callable

from sentinel.model import ProjectInstance
from sentinel.scheduling.priority_rules import (
    PRIORITY_RULES,
    grpw_priorities,
    lft_priorities,
    lst_priorities,
    mts_priorities,
)

Builder = Callable[..., ProjectInstance]


def test_tiny_priority_values(tiny: ProjectInstance) -> None:
    # tiny: 0 -> {1, 2}, 1 -> 3, 2 -> 4, 3 -> 4; p = (0, 3, 2, 4, 0); LB0 = 7.
    assert lft_priorities(tiny) == (0, 3, 7, 7, 7)
    assert lst_priorities(tiny) == (0, 0, 5, 3, 7)
    assert mts_priorities(tiny) == (4, 2, 1, 1, 0)
    assert grpw_priorities(tiny) == (5, 7, 2, 4, 0)


def test_mts_counts_each_transitive_successor_once(build: Builder) -> None:
    # Diamond 0 -> {1, 2} -> 3 -> 4: activity 0 reaches 3 and 4 along two paths.
    inst = build([0, 1, 1, 1, 0], [[0], [1], [1], [1], [0]], [[1, 2], [3], [3], [4], []])
    assert mts_priorities(inst) == (4, 2, 2, 1, 0)


def test_rule_directions() -> None:
    assert {name: rule.lower_is_better for name, rule in PRIORITY_RULES.items()} == {
        "lft": True,
        "lst": True,
        "mts": False,
        "grpw": False,
    }
    assert all(rule.name == name for name, rule in PRIORITY_RULES.items())
