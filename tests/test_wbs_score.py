"""Scores of an extraction (WP6a, RQ1): a perturbed truth gives the expected numbers, the truth
is exact, broken answers score zero, and the downstream CP-SAT makespans are checked."""

import json
import math
from collections.abc import Callable
from typing import Any

import pytest

from sentinel.model import ProjectInstance
from sentinel.wbs.extract import Extraction, to_instance, validate_extraction
from sentinel.wbs.narrate import activity_names, truth
from sentinel.wbs.score import CpsatSettings, cpsat_makespan, makespan_error, read_answer, score

Builder = Callable[..., ProjectInstance]
SEED = 5


def synthetic(build: Builder) -> ProjectInstance:
    """Nine real activities over four roles and 11 real precedences (as in test_wbs_narrate)."""
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


def answer_of(instance: ProjectInstance) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(truth(instance, SEED).model_dump_json())
    return data


def entry(data: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(a for a in data["activities"] if a["name"] == name)
    return found


def test_scoring_a_perturbed_truth_gives_the_expected_numbers(build: Builder) -> None:
    """One edge removed (1 -> 4), one duration changed (activity 2), one name changed
    (activity 9, whose predecessors are 7 and 8): 8 of 9 activities match both ways; of the
    9 true edges between matched activities (11 minus the two into 9) the answer has 8, all
    correct; 7 of 8 durations and every crew are right."""
    instance = synthetic(build)
    names = activity_names(instance, SEED)
    data = answer_of(instance)
    entry(data, names[4])["predecessors"].remove(names[1])
    entry(data, names[2])["duration_days"] += 1
    for activity in data["activities"]:
        if activity["name"] == names[9]:
            activity["name"] = "Write release notes"
        activity["predecessors"] = [
            "Write release notes" if p == names[9] else p for p in activity["predecessors"]
        ]
    issues = validate_extraction(data)
    assert issues == []
    s = score(data, truth(instance, SEED), issues)
    assert (s.n_true, s.n_extracted, s.n_matched) == (9, 9, 8)
    assert s.unmatched_true == (names[9],) and s.unmatched_extracted == ("Write release notes",)
    assert (s.all_true_edges, s.true_edges, s.extracted_edges, s.correct_edges) == (11, 9, 8, 8)
    assert s.activity_recall == s.activity_precision == pytest.approx(8 / 9)
    assert s.edge_precision == 1.0 and s.edge_recall == pytest.approx(8 / 9)
    assert s.edge_f1 == pytest.approx(16 / 17)
    assert s.duration_accuracy == pytest.approx(7 / 8) and s.crew_accuracy == 1.0
    assert s.team_accuracy == 1.0 and s.team_exact and s.valid and not s.exact


def test_the_truth_is_exact_and_names_match_after_normalisation(build: Builder) -> None:
    instance = synthetic(build)
    exact = score(answer_of(instance), truth(instance, SEED), [])
    assert exact.exact and exact.edge_f1 == exact.activity_recall == exact.crew_accuracy == 1.0
    data = answer_of(instance)
    data["activities"].reverse()
    for activity in data["activities"]:
        activity["name"] = activity["name"].upper() + "."
        activity["crew"] = {f"{role.title()}s": n for role, n in activity["crew"].items()}
    data["team"] = [{"role": m["role"].upper(), "count": m["count"]} for m in data["team"]]
    assert score(data, truth(instance, SEED), []).exact
    wrong_team = answer_of(instance)
    wrong_team["team"][3]["count"] -= 1
    wrong_team["team"].append({"role": "designer", "count": 1})
    s = score(wrong_team, truth(instance, SEED), [])
    assert s.team_accuracy == 0.75 and not s.team_exact and not s.exact


def test_broken_answers_score_zero_and_unmatched_entries_count(build: Builder) -> None:
    instance = synthetic(build)
    true = truth(instance, SEED)
    for broken in (None, [], {"team": "x"}):
        s = score(broken, true, [])
        assert (s.n_extracted, s.activity_recall, s.activity_precision, s.edge_f1) == (0, 0, 0, 0)
        assert math.isnan(s.duration_accuracy) and not s.exact
    data = answer_of(instance)
    data["activities"][0]["duration_days"] = "long"  # this entry alone is invalid
    data["activities"].append(dict(data["activities"][1]))  # a duplicate does not match twice
    s = score(data, true, validate_extraction(data))
    assert (s.n_extracted, s.n_matched, s.valid) == (10, 8, False)
    assert s.unmatched_extracted[0] == "#0 (invalid entry)" and len(s.unmatched_extracted) == 2
    looped = answer_of(instance)
    entry(looped, activity_names(instance, SEED)[3])["predecessors"].append(
        activity_names(instance, SEED)[3]
    )
    s = score(looped, true, validate_extraction(looped))
    assert (s.extracted_edges, s.correct_edges) == (12, 11) and not s.valid
    assert read_answer(
        {"team": [{"role": "tester", "count": 1}, {"role": "Testers", "count": 4}]}
    ).team == {"tester": 1}


def test_downstream_makespans_come_from_checked_cpsat_schedules(build: Builder) -> None:
    instance = synthetic(build)
    data = answer_of(instance)
    settings = CpsatSettings(deterministic_time_limit=1.0)
    assert validate_extraction(data) == []
    extracted = to_instance(Extraction.model_validate(data), name="extracted")
    true_makespan = cpsat_makespan(instance, settings)
    assert cpsat_makespan(extracted, settings).makespan == true_makespan.makespan
    assert true_makespan.status == "OPTIMAL"
    entry(data, activity_names(instance, SEED)[9])["duration_days"] = 20
    longer = to_instance(Extraction.model_validate(data), name="longer")
    error = makespan_error(cpsat_makespan(longer, settings).makespan, true_makespan.makespan)
    assert error == pytest.approx(10 / true_makespan.makespan)
    with pytest.raises(ValueError):
        makespan_error(3, 0)
