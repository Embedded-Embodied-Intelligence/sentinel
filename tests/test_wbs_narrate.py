"""Narrator (WP6a, RQ1 inputs): deterministic texts in both styles whose every fact a template
parser reads back exactly once, on a synthetic instance and on the 40 study instances."""

import re
from collections.abc import Callable

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.experiments.runs import derive_seed
from sentinel.model import ProjectInstance
from sentinel.wbs.extract import Extraction, to_instance
from sentinel.wbs.narrate import (
    ROLE_NAMES,
    STYLES,
    VOCABULARY,
    activity_names,
    dominant_role,
    narrate,
    number_words,
    parse_narration,
    parse_number,
    truth,
)

Builder = Callable[..., ProjectInstance]


def synthetic(build: Builder) -> ProjectInstance:
    """Nine real activities over four roles, with joins, forks and crews of one to four roles."""
    return build(
        durations=[0, 3, 5, 1, 2, 4, 6, 1, 7, 10, 0],
        demands=[
            [0, 0, 0, 0],
            [2, 0, 0, 1],
            [0, 3, 0, 0],
            [0, 0, 1, 0],
            [1, 1, 1, 1],
            [0, 0, 2, 0],
            [0, 0, 0, 4],
            [5, 0, 0, 0],
            [0, 2, 0, 2],
            [1, 0, 1, 0],
            [0, 0, 0, 0],
        ],
        successors=[[1, 2, 3], [4, 5], [5, 6], [6], [7], [7, 8], [8], [9], [9], [10], []],
        capacities=(6, 4, 3, 25),
    )


def canonical(extraction: Extraction) -> tuple[object, object]:
    team = {member.role: member.count for member in extraction.team}
    activities = {
        a.name: (a.duration_days, dict(sorted(a.crew.items())), frozenset(a.predecessors))
        for a in extraction.activities
    }
    return team, activities


def assert_same_instance(rebuilt: ProjectInstance, original: ProjectInstance, seed: int) -> None:
    """`rebuilt` (ids in text order) is `original` up to the ids: same durations, demands per
    role and real precedences under the narrator's names."""
    names = activity_names(original, seed)
    ids = {a.name: a.id for a in rebuilt.activities[1:-1]}
    assert sorted(ids) == sorted(names.values())
    as_rebuilt = {j: ids[name] for j, name in names.items()}
    roles = [ROLE_NAMES.index(role.name) for role in rebuilt.roles]
    assert [rebuilt.roles[roles.index(k)].capacity for k in range(len(roles))] == [
        role.capacity for role in original.roles
    ]
    for j, mapped in as_rebuilt.items():
        old, new = original.activities[j], rebuilt.activities[mapped]
        assert new.duration == old.duration
        assert [new.demands[roles.index(k)] for k in range(len(roles))] == list(old.demands)
        old_succ = {as_rebuilt[s] for s in old.successors if s in as_rebuilt}
        assert {s for s in new.successors if s != rebuilt.sink_id} == old_succ


@pytest.mark.parametrize("style", STYLES)
def test_a_parser_of_the_templates_recovers_the_instance_exactly(
    build: Builder, style: str
) -> None:
    instance = synthetic(build)
    for seed in range(20):
        text = narrate(instance, style=style, seed=seed)  # type: ignore[arg-type]
        parsed = parse_narration(text)
        assert canonical(parsed) == canonical(truth(instance, seed))
        assert_same_instance(to_instance(parsed, name="rebuilt"), instance, seed)


def test_the_same_seed_gives_the_same_text_and_names_are_shared_by_the_styles(
    build: Builder,
) -> None:
    instance = synthetic(build)
    for style in STYLES:
        assert narrate(instance, style=style, seed=3) == narrate(instance, style=style, seed=3)
        assert narrate(instance, style=style, seed=3) != narrate(instance, style=style, seed=4)
    names = activity_names(instance, 3)
    for style in STYLES:
        text = narrate(instance, style=style, seed=3)
        assert set(re.findall(r'"([^"]+)"', text)) == set(names.values())
    assert activity_names(instance, 3) != activity_names(instance, 4)


def test_names_are_unique_plain_and_from_the_dominant_roles_vocabulary(build: Builder) -> None:
    instance = synthetic(build)
    for seed in range(50):
        names = activity_names(instance, seed)
        assert len(set(names.values())) == instance.n_real
        for j, name in names.items():
            verbs, objects = VOCABULARY[dominant_role(instance.activities[j])]
            assert any(name == f"{verb} {thing}" for verb in verbs for thing in objects)
            assert not re.search(r'[,.\d"]|\band\b', name)
    assert dominant_role(instance.activities[4]) == 0  # a tie goes to the lower role
    assert dominant_role(instance.activities[8]) == 1


def test_the_parser_rejects_a_fact_stated_twice_or_text_outside_the_templates(
    build: Builder,
) -> None:
    instance = synthetic(build)
    narrative = narrate(instance, style="narrative", seed=1)
    sentence = next(s for s in re.split(r"(?<=\.)\s+", narrative) if "working day" in s)
    with pytest.raises(ValueError, match="twice"):
        parse_narration(narrative.rstrip("\n") + " " + sentence + "\n")
    with pytest.raises(ValueError, match="templates match"):
        parse_narration(narrative.rstrip("\n") + " The weather is fine.\n")
    structured = narrate(instance, style="structured", seed=1)
    line = next(line for line in structured.splitlines() if line.startswith('- Predecessors: "'))
    with pytest.raises(ValueError, match="twice"):
        parse_narration(structured.replace(line, line + ", " + line.split(": ", 1)[1], 1))


def test_the_narrative_states_dependencies_in_both_directions_and_numbers_in_words(
    build: Builder,
) -> None:
    instance = synthetic(build)
    texts = [narrate(instance, style="narrative", seed=seed) for seed in range(20)]
    joined = " ".join(texts)
    assert "It can only start once" in joined or "It depends on" in joined
    assert "must be finished before" in joined or "cannot start until it is complete" in joined
    assert re.search(r"\b(one|two|three|four|five|six|seven) working days?\b", joined)
    assert re.search(r"\b\d+ working days?\b", joined)
    structured = narrate(instance, style="structured", seed=0)
    blocks = [line for line in structured.splitlines() if line.startswith("Activity ")]
    names = activity_names(instance, 0)
    order = [j for j in instance.topological_order() if j in names]
    assert blocks == [f'Activity "{names[j]}"' for j in order]


def test_number_words_read_back() -> None:
    assert [number_words(n) for n in (0, 7, 13, 20, 59, 99)] == [
        "zero",
        "seven",
        "thirteen",
        "twenty",
        "fifty-nine",
        "ninety-nine",
    ]
    assert all(parse_number(number_words(n)) == n == parse_number(str(n)) for n in range(100))
    with pytest.raises(ValueError):
        number_words(100)


@pytest.mark.data
def test_the_round_trip_is_exact_on_the_40_study_instances_in_both_styles(
    psplib_root: object,
) -> None:
    """RQ1 instances (J30 every 12th): every fact of each instance appears in the text exactly
    once, since the parser recovers the instance and rejects any fact stated twice."""
    stems = list_instances("j30", psplib_root)[::12]  # type: ignore[arg-type]
    assert len(stems) == 40
    for stem in stems:
        instance = load_psplib(instance_path("j30", stem, psplib_root))  # type: ignore[arg-type]
        seed = derive_seed(2026, "narrate", "j30", stem)
        for style in STYLES:
            text = narrate(instance, style=style, seed=seed)
            assert text == narrate(instance, style=style, seed=seed)
            parsed = parse_narration(text)
            assert canonical(parsed) == canonical(truth(instance, seed)), (stem, style)
            assert_same_instance(to_instance(parsed, name=stem), instance, seed)
