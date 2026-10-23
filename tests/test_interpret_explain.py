"""Role 3 of the interpretation layer (spec section 10.4): rendering a decision record and
checking an explanation's faithfulness."""

import json
from collections.abc import Callable

import pytest
from test_sentinel import SMALL, lively_observations

from sentinel.agent.decide import CandidateRecord, DecisionRecord, Needs
from sentinel.interpret.explain import (
    ExplainSettings,
    Explanation,
    check,
    explain,
    render_record,
)
from sentinel.llm import FakeLlmClient
from sentinel.model import ProjectInstance
from sentinel.policies.base import Decision, Reseq, Subst
from sentinel.simulation.state import Observation

Builder = Callable[..., ProjectInstance]


def candidate(
    label: str, kind: str, p: float, tardiness: float, **extra: object
) -> CandidateRecord:
    values: dict[str, object] = {
        "label": label,
        "kind": kind,
        "level": 0,
        "delay": 0,
        "deviation": 0.0,
        "substituted": 0,
        "scope_loss": 0.0,
        "rollouts": 100,
        "p_on_time": p,
        "capped": min(p, 0.8),
        "tardiness": tardiness,
        "mean_cost": 700.0,
        "overrun": 0.0,
        "utility": p,
        "dropped": False,
        "decision": Decision(),
        "eliminated": None,
    }
    return CandidateRecord.model_validate(values | extra)


@pytest.fixture
def case(build: Builder) -> tuple[DecisionRecord, Observation]:
    observation = lively_observations(build, count=1)[0]
    subst = Decision(operations=(Subst(activity=4, workers=(7,)), Reseq(starts={})))
    record = DecisionRecord(
        day=observation.day,
        deliberated=True,
        rule="lexicographic",
        reason="tardiness",
        chosen="SUBST-ALL+RESEQ-M",
        decision=subst,
        runner_up="SHIFT",
        needs=Needs(deadline=0.38, budget=0.0, p_on_time=0.42, rollouts=100, met=False),
        candidates=(
            candidate("NOOP", "noop", 0.42, 3.1, eliminated="on_time"),
            candidate("SHIFT", "shift", 0.58, 1.9, eliminated="tardiness"),
            candidate(
                "SUBST-ALL+RESEQ-M",
                "subst_all_reseq_m",
                0.61,
                1.25,
                level=2,
                deviation=2.5,
                substituted=1,
                decision=subst,
            ),
        ),
        tied=("SUBST-ALL+RESEQ-M",),
    )
    return record, observation


def answer(summary: str, *facts: tuple[str, object]) -> dict[str, object]:
    return {"summary": summary, "cited_facts": [{"kind": k, "value": v} for k, v in facts]}


def test_a_faithful_explanation_passes_every_check(
    case: tuple[DecisionRecord, Observation],
) -> None:
    record, observation = case
    rendered = render_record(record, observation, SMALL)
    assert '"SUBST-ALL+RESEQ-M" (replace 1 absent crew member of activity 4, then' in rendered.text
    assert "Deciding component: tardiness." in rendered.text
    faithful = answer(
        'The agent chose "SUBST-ALL+RESEQ-M": the absent crew member is replaced and the plan '
        "re-sequenced, which keeps the chance of finishing on time at 61 % and cuts the expected "
        "delay to 1.25 days, against 1.9 days for SHIFT.",
        ("chosen_action", "SUBST-ALL+RESEQ-M"),
        ("p_on_time", "61 %"),
        ("tardiness_days", 1.25),
        ("budget_overrun", 0),
        ("alternative", "shift"),
        ("alternative_p_on_time", 0.58),
        ("deciding_component", "tardiness"),
    )
    result = check(faithful, record, rendered)
    assert result.fully_faithful, result
    assert result.numbers == 3 and result.hallucinated == 0 and result.words < 80


def test_a_hallucinating_explanation_fails_the_right_checks(
    case: tuple[DecisionRecord, Observation],
) -> None:
    record, observation = case
    rendered = render_record(record, observation, SMALL)
    assert 4.44 not in rendered.values and 93.0 not in rendered.values
    wrong = answer(
        "Substituting is 93 % safer and saves 4.44 days of delay.",
        ("chosen_action", "SUBST-ALL"),
        ("p_on_time", 0.71),
        ("deciding_component", "on_time"),
        ("alternative_p_on_time", "58%"),
    )
    result = check(wrong, record, rendered)
    assert not result.fully_faithful
    assert result.hallucinated == 2 and not result.chosen_named and not result.component_right
    assert [f.correct for f in result.facts] == [False, False, False, True]
    invalid = check({"summary": "No facts."}, record, rendered)
    assert not invalid.valid and not invalid.fully_faithful


def test_an_only_noop_record_is_rendered_and_checked_from_its_needs(
    case: tuple[DecisionRecord, Observation],
) -> None:
    record, observation = case
    lonely = record.model_copy(
        update={"candidates": (), "chosen": "NOOP", "runner_up": None, "reason": "only_candidate"}
    )
    rendered = render_record(lonely, observation, SMALL)
    assert "the only valid candidate" in rendered.text
    result = check(
        answer(
            "Only keeping the plan was possible; the chance of finishing on time is 0.42.",
            ("chosen_action", "NOOP"),
            ("p_on_time", 0.42),
            ("deciding_component", "only_candidate"),
            ("alternative", "SHIFT"),
        ),
        lonely,
        rendered,
    )
    assert [f.correct for f in result.facts] == [True, True, True, False]


def test_an_explanation_call_goes_through_the_llm_layer(
    case: tuple[DecisionRecord, Observation],
) -> None:
    record, observation = case
    rendered = render_record(record, observation, SMALL)
    reply = answer("Fine.", ("chosen_action", record.chosen))
    client = FakeLlmClient([json.dumps(reply)])
    response = explain(client, rendered, seed=1, settings=ExplainSettings(max_tokens=256))
    assert isinstance(response.value, Explanation)
    assert client.requests[0].messages[1].content == rendered.text
