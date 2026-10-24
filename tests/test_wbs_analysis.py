"""RQ1 error analysis (WP7): on a hand-made answer with known missing edges, the outcomes,
recall by side, number form and distance, the predecessor side's share of the missed edges and
the carrying of a session's last answer to later rounds."""

import json
from collections.abc import Sequence
from typing import Any

from sentinel.llm import FakeLlmClient
from sentinel.wbs.analysis import DISTANCE_BINS, Rate, answers_by_round, edge_outcomes, error_cells
from sentinel.wbs.extract import Extraction, ExtractionSettings, repair
from sentinel.wbs.narrate import EdgePhrasing
from sentinel.wbs.score import score


def act(name: str, predecessors: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "name": name,
        "duration_days": 2,
        "crew": {"tester": 1},
        "predecessors": list(predecessors),
    }


def project(*activities: dict[str, Any]) -> dict[str, Any]:
    return {"team": [{"role": "tester", "count": 2}], "activities": list(activities)}


TRUTH_DATA = project(
    act("Plan sprint"),
    act("Build login", ["Plan sprint"]),
    act("Build search", ["Plan sprint"]),
    act("Test release", ["Build login", "Build search"]),
    act("Write notes", ["Build login"]),
)
TRUTH = Extraction.model_validate(TRUTH_DATA)
PHRASINGS = (
    EdgePhrasing("Plan sprint", "Build login", "successor", "words", 0),
    EdgePhrasing("Plan sprint", "Build search", "predecessor", "digits", 1),
    EdgePhrasing("Build login", "Test release", "predecessor", "words", 4),
    EdgePhrasing("Build search", "Test release", "successor", "digits", 7),
    EdgePhrasing("Build login", "Write notes", "predecessor", "digits", 2),
)


def test_the_outcomes_mark_the_missing_edges_and_skip_unmatched_activities() -> None:
    answer = project(
        act("Plan sprint"),
        act("build LOGIN", ["Plan sprint"]),
        act("Build search"),  # misses Plan sprint -> Build search (predecessor side)
        act("Test release", ["Build search"]),  # misses Build login (predecessor side)
        act("Write a note", ["Build login"]),  # unmatched: its edge is not scored
    )
    outcomes = edge_outcomes(answer, TRUTH, PHRASINGS)
    assert [(o.phrasing.successor, o.found) for o in outcomes] == [
        ("Build login", True),
        ("Build search", False),
        ("Test release", False),
        ("Test release", True),
    ]
    scores = score(answer, TRUTH, [])
    assert (scores.correct_edges, scores.true_edges) == (2, 4)  # the edges of the recall
    assert edge_outcomes(None, TRUTH, PHRASINGS) == ()

    cell, other = error_cells(
        [
            ("j301_1", "fake", "narrative", [outcomes]),
            ("j302_3", "fake", "narrative", [edge_outcomes(TRUTH_DATA, TRUTH, PHRASINGS)]),
            ("j301_1", "fake", "structured", [outcomes]),
        ]
    )
    assert (cell.sessions, other.style, other.sessions) == (2, "structured", 1)
    assert cell.rate() == Rate(7, 9) and cell.rate().missing == 2
    assert cell.side("successor") == Rate(4, 4) and cell.side("predecessor") == Rate(3, 5)
    assert cell.numbers("words") == Rate(3, 4) and cell.numbers("digits") == Rate(4, 5)
    assert cell.missing_predecessor_share == 1.0 and cell.predecessor_share == 5 / 9
    assert [cell.distance(low, high) for low, high in DISTANCE_BINS] == [
        Rate(2, 2),
        Rate(2, 3),
        Rate(1, 2),
        Rate(2, 2),
    ]
    assert cell.distance(3, 5, "predecessor") == Rate(1, 2)
    assert cell.by_instance(lambda p: p.side == "predecessor") == {
        "j301_1": Rate(0, 2),
        "j302_3": Rate(3, 3),
    }


def test_a_session_that_ended_keeps_its_last_answer_in_later_rounds() -> None:
    invalid = project(act("Plan sprint", ["Nowhere"]))
    client = FakeLlmClient([json.dumps(invalid), json.dumps(TRUTH_DATA)])
    session = repair(client, "A description.", seed=1, settings=ExtractionSettings(max_tokens=256))
    assert len(session.rounds) == 2
    answers = answers_by_round(session, 3)
    assert answers[0] == invalid and answers[1] == answers[2] == answers[3] == TRUTH_DATA
