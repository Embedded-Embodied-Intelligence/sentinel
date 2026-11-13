"""Role 4, editing a person's text for an audience (spec section 11.9, ADR-0038)."""

import json

from sentinel.interpret.redaction import (
    AUDIENCES,
    RedactSettings,
    redact,
    redact_messages,
    redact_reporting,
)
from sentinel.llm import FakeLlmClient


def test_every_audience_has_its_style_and_the_prompt_is_english() -> None:
    for audience in AUDIENCES:
        system, user = redact_messages("Tekst raportu.", audience, "pl")
        assert system.role == "system" and user.content == "Tekst raportu."
        assert "Polish" in system.content and "$" not in system.content
        assert '{"text": "<the edited text>"} only' in system.content
    board = redact_messages("x", "board", "en")[0].content
    assert "management board" in board and "English" in board
    reporting = redact_messages("x", "edit", "pl", report_changes=True)[0].content
    assert '"changes"' in reporting and "list every change" in reporting


def test_the_answer_is_the_edited_text_only() -> None:
    client = FakeLlmClient([json.dumps({"text": "Krótszy tekst."})])
    response = redact(
        client, "Długi tekst.", "edit", language="pl", seed=1, settings=RedactSettings()
    )
    assert response.value is not None and response.value.text == "Krótszy tekst."
    extra = FakeLlmClient([json.dumps({"text": "T", "changes": []})])
    rejected = redact(extra, "T", "edit", language="pl", seed=1, settings=RedactSettings())
    assert rejected.value is None  # a list of changes is not part of the application's answer
    answer = {"text": "T2", "changes": [{"before": "T", "after": "T2"}]}
    reporting = redact_reporting(
        FakeLlmClient([json.dumps(answer)]),
        "T",
        "edit",
        language="pl",
        seed=1,
        settings=RedactSettings(),
    )
    assert reporting.value is not None and reporting.value.changes[0].after == "T2"
