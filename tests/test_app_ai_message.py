"""A check-in message for the AI (WP11; the live runs: a small model wrote day 4 for the Friday of
day 14 and 1.3 for 3 more of 5 days, and a repair round without the answer could not say why)."""

from datetime import date

from app_cases import DEV, TESTER, checked_in, planned, small

from sentinel.app.llm import LiveContext, work_left
from sentinel.app.models import CheckIn, TaskReport
from sentinel.interpret.events import ISSUE_KINDS, TeamMessage, withheld_issue
from sentinel.llm.core import ErrorDetail


def test_a_check_in_message_is_read_with_the_days_and_factors_worked_out() -> None:
    project = small()
    project = checked_in(
        planned(project),
        CheckIn(
            date=date(2026, 11, 3),
            tasks=(TaskReport(task="T1", status="in_progress", percent=20.0),),
        ),
    )
    context = LiveContext(project, date(2026, 11, 4))  # a Wednesday, working day 2
    text = context.render(TeamMessage(day=context.day, author=0, text="Ada is away."))
    assert "Today is day 2, a Wednesday." in text
    assert "day 4 Friday, day 5 Monday" in text and "(piątek)" not in text
    left = work_left(project)["T1"]
    assert f"if it takes N days longer, the factor is: 1 day {(left + 1) / left:.2f}" in text
    assert f"3 days {(left + 3) / left:.2f}" in text
    assert DEV in text and TESTER in text
    polish = small().model_copy(
        update={"settings": small().settings.model_copy(update={"language": "pl"})}
    )
    context = LiveContext(planned(polish), date(2026, 11, 4))
    text = context.render(TeamMessage(day=context.day, author=0, text="Ady nie będzie."))
    assert "day 4 Friday (piątek)" in text


def test_a_repair_round_says_what_a_withheld_issue_asks_for_without_its_values() -> None:
    for kind in ISSUE_KINDS:
        issue = withheld_issue(ErrorDetail("events[0]", kind, kind))
        assert issue.message.startswith(f'events[0] has the issue "{kind.replace("_", " ")}"; ')
        assert issue.message.endswith("give the complete answer again.")
    assert (
        "day number after today"
        in withheld_issue(ErrorDetail("events[0]", "impossible_day", "impossible_day")).message
    )
