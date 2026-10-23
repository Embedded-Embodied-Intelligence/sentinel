"""Extraction (WP6a, RQ1): the validator catches every issue type on hand-made answers, a valid
answer becomes the instance, and the repair loop stops on a valid answer or after 3 rounds."""

import json
from collections.abc import Sequence
from typing import Any

import pytest

from sentinel.llm import FakeLlmClient, FakeReply, Message, Reply, Request, RequestTooLarge
from sentinel.model import validate_schedule
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.wbs.extract import (
    ISSUE_KINDS,
    MAX_LISTED_ISSUES,
    Extraction,
    ExtractionSettings,
    Issue,
    format_issues,
    normalise_name,
    normalise_role,
    repair,
    single_shot,
    to_instance,
    validate_extraction,
)

TEAM = [{"role": "backend developer", "count": 3}, {"role": "tester", "count": 2}]
SETTINGS = ExtractionSettings(max_tokens=512)
TEXT = "A project description."


def act(
    name: str, duration: object = 2, crew: object = None, predecessors: Sequence[str] = ()
) -> dict[str, Any]:
    return {
        "name": name,
        "duration_days": duration,
        "crew": {"backend developer": 1} if crew is None else crew,
        "predecessors": list(predecessors),
    }


def project(*activities: dict[str, Any], team: object = None) -> dict[str, Any]:
    return {"team": TEAM if team is None else team, "activities": list(activities)}


VALID = project(
    act("Build payment API", 4, {"backend developers": 2}),
    act("Test payment flow", 2, {"Tester": 1}, ["build payment api"]),
    act("Review release", 1, {"tester": 2, "backend developer": 0}, ["Test payment flow"]),
)


def kinds(data: object) -> list[str]:
    return [issue.kind for issue in validate_extraction(data)]


def test_the_validator_catches_every_issue_type_on_hand_made_cases() -> None:
    assert validate_extraction(VALID) == []
    missing = project(act("A"))
    del missing["activities"][0]["duration_days"]
    cases: dict[str, object] = {
        "missing_field": missing,
        "invalid_field": project(act("A", duration="five")),
        "duplicate_role": project(act("A"), team=[*TEAM, {"role": "testers", "count": 1}]),
        "unknown_role": project(act("A", crew={"designer": 1})),
        "negative_count": project(act("A", crew={"tester": -1})),
        "duplicate_name": project(act("A"), act(" a ")),
        "unknown_name": project(act("A", predecessors=["B"])),
        "cycle": project(
            act("A", predecessors=["C"]), act("B", predecessors=["A"]), act("C", predecessors=["B"])
        ),
        "non_positive_duration": project(act("A", duration=0)),
        "crew_above_capacity": project(act("A", crew={"tester": 3})),
    }
    for kind, data in cases.items():
        assert kinds(data) == [kind], kind
    assert kinds(project(act("A", duration=-1))) == ["non_positive_duration"]
    assert kinds([]) == ["invalid_field"]  # not an object
    assert kinds(project(act(""))) == ["missing_field"]
    assert kinds(project(act("A"), team=[{"role": " ", "count": 1}])) == [
        "missing_field",
        "unknown_role",
    ]
    seen = set(cases) | {"invalid_json"}  # invalid_json: see the repair-loop test
    assert seen == set(ISSUE_KINDS)


def test_issue_messages_name_the_activity_and_list_the_cycle() -> None:
    missing = project(act("Build payment API"))
    del missing["activities"][0]["crew"]
    (issue,) = validate_extraction(missing)
    assert (
        issue.activity == "Build payment API" and '"activities[0].crew" is missing' in issue.message
    )
    cycle = project(
        act("A", predecessors=["C"]),
        act("B", predecessors=["A"]),
        act("C", predecessors=["B"]),
        act("D", predecessors=["D"]),
    )
    found = [i for i in validate_extraction(cycle) if i.kind == "cycle"]
    assert [i.cycle for i in found] == [("A", "B", "C", "A"), ("D", "D")]
    assert '"A" -> "B" -> "C" -> "A"' in found[0].message
    (unknown,) = validate_extraction(project(act("A", predecessors=["Z"])))
    assert unknown.message == (
        'The activity "A" lists the predecessor "Z", which is not an activity of the project.'
    )


def test_names_match_after_normalisation() -> None:
    assert normalise_name("  Build  the PAYMENT-API! ") == "build the payment api"
    assert (
        normalise_role("DevOps Engineers") == "devops engineer" == normalise_role("devops engineer")
    )
    assert normalise_role("tester") == normalise_role("Testers") == "tester"


def test_a_valid_extraction_becomes_an_instance_with_source_and_sink() -> None:
    extraction = Extraction.model_validate(VALID)
    instance = to_instance(extraction, name="extracted")
    assert [role.name for role in instance.roles] == ["backend developer", "tester"]
    assert [role.capacity for role in instance.roles] == [3, 2]
    names = [a.name for a in instance.activities]
    assert names[1:4] == ["Build payment API", "Test payment flow", "Review release"]
    assert [a.duration for a in instance.activities] == [0, 4, 2, 1, 0]
    assert [a.demands for a in instance.activities] == [(0, 0), (2, 0), (0, 1), (0, 2), (0, 0)]
    assert [a.successors for a in instance.activities] == [(1,), (2,), (3,), (4,), ()]
    schedule = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
    assert validate_schedule(instance, schedule) == [] and schedule.makespan(instance) == 7
    with pytest.raises(ValueError, match="issues"):
        to_instance(Extraction.model_validate(project(act("A", predecessors=["B"]))), name="x")
    empty = to_instance(Extraction.model_validate(project()), name="empty")
    assert empty.n_real == 0 and empty.activities[0].successors == (1,)


def test_the_repair_loop_stops_on_a_valid_answer() -> None:
    first = project(
        act("Build payment API", 4, {"backend developer": 2}),
        act("Test payment flow", 2, {"tester": 1}, ["Build API"]),
    )
    second = json.loads(json.dumps(first))
    second["activities"][1]["predecessors"] = ["Build payment API"]
    client = FakeLlmClient([json.dumps(first, indent=2), json.dumps(second)])
    session = repair(client, TEXT, seed=11, settings=SETTINGS)
    assert [len(r.issues) for r in session.rounds] == [1, 0] and session.repair_rounds == 1
    assert session.single_shot.issues[0].kind == "unknown_name" and session.final.valid
    assert session.stopped is None
    first_call, repair_call = client.requests
    assert [m.role for m in first_call.messages] == ["system", "user"]
    assert [m.role for m in repair_call.messages] == ["system", "user", "assistant", "user"]
    assert repair_call.messages[:2] == first_call.messages
    assert repair_call.messages[2].content == json.dumps(first, separators=(",", ":"))
    assert session.single_shot.issues[0].message in repair_call.messages[3].content
    assert {first_call.seed, repair_call.seed} == {11}
    valid = FakeLlmClient([json.dumps(second)])
    assert repair(valid, TEXT, seed=1, settings=SETTINGS).repair_rounds == 0
    assert len(valid.requests) == 1


def test_the_repair_loop_stops_after_three_rounds() -> None:
    answers = [
        "not json",
        FakeReply('{"team": [', "length"),
        json.dumps(project(act("A", 0))),
        "[]",
    ]
    client = FakeLlmClient(answers)
    session = repair(client, TEXT, seed=2, settings=SETTINGS)
    assert session.repair_rounds == 3 and len(client.requests) == 4 and not session.final.valid
    assert [r.issues[0].kind for r in session.rounds] == [
        "invalid_json",
        "invalid_json",
        "non_positive_duration",
        "invalid_field",
    ]
    assert "cut off" in session.rounds[1].issues[0].message
    assert (
        client.requests[2].messages[2].content == '{"team": ['
    )  # unparsed answers go back as text
    shot = single_shot(FakeLlmClient(answers), TEXT, seed=2, settings=SETTINGS)
    assert shot.index == 0 and shot.issues == session.single_shot.issues


def test_a_repair_round_that_cannot_fit_ends_the_session() -> None:
    class Limited(FakeLlmClient):
        def _send(self, request: Request) -> Reply:
            if len(request.messages) > 2:
                raise RequestTooLarge("over the limit")
            return super()._send(request)

    session = repair(Limited(["not json"]), TEXT, seed=2, settings=SETTINGS)
    assert session.repair_rounds == 0 and session.stopped is not None
    assert session.stopped.startswith("request too large")


def test_repair_messages_list_at_most_forty_issues() -> None:
    issues = [Issue("unknown_name", f"issue {i}") for i in range(MAX_LISTED_ISSUES + 5)]
    lines = format_issues(issues).splitlines()
    assert (
        len(lines) == MAX_LISTED_ISSUES + 1
        and lines[-1] == "- ... and 5 more issues of these kinds."
    )
    assert Message(role="user", content=format_issues(issues[:1])).content == "- issue 0"
