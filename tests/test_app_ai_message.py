"""A check-in message for the AI (WP11; the live runs: a small model wrote day 4 for the Friday of
day 14 and 1.3 for 3 more of 5 days, and a repair round without the answer could not say why)."""

from datetime import date

from app_cases import DEV, TESTER, checked_in, planned, small

from sentinel.app.llm import LiveContext, work_left
from sentinel.app.models import CheckIn, TaskReport
from sentinel.interpret.events import ISSUE_KINDS, AbsenceEvent, TeamMessage, withheld_issue
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
    assert "until Friday → 5, back on Friday → 4; until Monday → 6" in text
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
    assert "until Friday (do piątku) → 5, back on Friday (wraca w piątek) → 4" in text


def test_until_a_weekday_is_away_through_it_and_back_on_a_weekday_is_back_that_day() -> None:
    """Spec section 11.3 (v2.1.5): "until Friday" gives Monday, "back on Friday" Friday."""
    project = planned(small())
    context = LiveContext(project, date(2026, 11, 4))  # a Wednesday, working day 2
    until, back = 5, 4  # the return days the rendered context gives for Friday
    draft = context.draft(
        [
            AbsenceEvent(type="absence", worker=0, return_day=until),
            AbsenceEvent(type="absence", worker=1, return_day=back),
        ],
        0,
    )
    assert [a.return_date for a in draft.absences] == [date(2026, 11, 9), date(2026, 11, 6)]
    assert [a.first_day for a in draft.absences] == [date(2026, 11, 4)] * 2


def test_a_repair_round_says_what_a_withheld_issue_asks_for_without_its_values() -> None:
    for kind in ISSUE_KINDS:
        issue = withheld_issue(ErrorDetail("events[0]", kind, kind))
        assert issue.message.startswith(f'events[0] has the issue "{kind.replace("_", " ")}"; ')
        assert issue.message.endswith("give the complete answer again.")
    assert (
        "day number after today"
        in withheld_issue(ErrorDetail("events[0]", "impossible_day", "impossible_day")).message
    )


def test_nothing_in_a_message_is_dropped_silently() -> None:
    """Task 12 of WP12 (B6): the parts the AI did not turn into an event are listed, and it asks
    about a name not in the team and about a growth that fits two tasks; the answer holds clause
    numbers only, never words of the message (invariant 7)."""
    from sentinel.app.llm import EVENTS, parse_live, split_clauses
    from sentinel.llm import FakeLlmClient

    text = "Marek jest na urlopie do środy, a testy potrwają 2 dni dłużej. Spotkanie w piątek."
    clauses = split_clauses(text, "pl")
    assert clauses == (
        "Marek jest na urlopie do środy",
        "testy potrwają 2 dni dłużej.",
        "Spotkanie w piątek.",
    )
    project = planned(small())
    context = LiveContext(project, date(2026, 11, 4), clauses)
    message = TeamMessage(day=context.day, author=0, text=text)
    assert "[2] testy potrwają 2 dni dłużej." in context.render(message)
    answers = [
        '{"events": [], "unparsed": [3, 9], "questions": [{"kind": "ambiguous_task", "clause":'
        ' 2, "candidates": [3], "extra_days": 2}]}',
        '{"events": [], "unparsed": [3], "questions": [{"kind": "unknown_person", "clause": 1,'
        ' "return_day": 5}, {"kind": "ambiguous_task", "clause": 2, "candidates": [1, 3],'
        ' "extra_days": 2}]}',
    ]
    final = parse_live(FakeLlmClient(answers), message, context, seed=1, settings=EVENTS)
    assert final.reading.issues == ()  # the first answer's issues were repaired
    draft = context.draft(final.reading.events, 0, final.unparsed, final.questions)
    assert draft.unparsed == (3,)
    person, task = draft.questions
    assert person.kind == "unknown_person" and person.return_date == date(2026, 11, 9)
    assert task.candidates == ("T1", "T3") and task.extra_days == 2
    assert "Marek" not in draft.model_dump_json()  # no word of the message is kept


def test_an_explanation_is_in_the_page_language_without_internal_terms() -> None:
    """Task 13 of WP12 (B7): the explanation is asked for in the page's language with the
    actions as the page names them; a text with an internal term is asked for once more, and
    if the second has one too, the page keeps its template explanation alone."""
    import json

    from app_cases import ABSENCE_CHECKIN, absence_recommendation, answer_from

    from sentinel.app import planning
    from sentinel.app.llm import LlmService
    from sentinel.llm import FakeLlmClient

    record = absence_recommendation().as_shown
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    observation = project.observation()
    params = planning.sentinel_params(project)
    roles = project.require_model().role_names
    clean = json.loads(answer_from(record))
    dirty = {**clean, "summary": "SUBST(1) wins: the makespan shrinks."}
    service = LlmService.__new__(LlmService)
    names = {"SUBST(1)": "Zastępstwo: Cleo przejmuje udział osoby nieobecnej (Ada)"}
    for answers, expected in (([dirty, clean], clean["summary"]), ([dirty, dirty], "")):
        fake = FakeLlmClient([json.dumps(answer) for answer in answers])
        service.client = lambda fake=fake: fake  # type: ignore[method-assign]
        result = service.explain(record, observation, params, roles, 7, language="pl", names=names)
        assert result.text == expected and len(fake.requests) == 2
        sent = fake.requests[0].messages
        assert 'Write the "summary" in Polish' in sent[0].content
        assert names["SUBST(1)"] in sent[1].content
        assert "uses SUBST, makespan" in fake.requests[1].messages[-1].content
    assert result.error == "internal_terms" and not result.valid


def test_a_description_gives_short_names_optional_tasks_and_their_sentences() -> None:
    """Task 14 of WP12 (B8): a name is at most six words with its sentence kept, an optional
    task is recognised, and the prompt states the calendar's facts ("about a week" is 5)."""
    import json

    from sentinel.app.llm import EXTRACTION, extract_live
    from sentinel.app.services import draft_definition
    from sentinel.llm import FakeLlmClient

    long = "dwóch programistów robi logowanie i uprawnienia przez tydzień"
    first = {
        "team": [{"role": "Developer", "count": 2}],
        "activities": [
            {"name": long, "duration_days": 5, "crew": {"Developer": 2}, "predecessors": []},
        ],
    }
    second = {
        "team": [{"role": "Developer", "count": 2}],
        "activities": [
            {
                "name": "Logowanie i uprawnienia",
                "description": long,
                "duration_days": 5,
                "crew": {"Developer": 2},
                "predecessors": [],
            },
            {
                "name": "Integracja z SMS",
                "description": "SMS — możemy z niego zrezygnować",
                "optional": True,
                "duration_days": 3,
                "crew": {"Developer": 1},
                "predecessors": ["Logowanie i uprawnienia"],
            },
        ],
    }
    fake = FakeLlmClient([json.dumps(first), json.dumps(second)])
    session = extract_live(fake, "Opis projektu.", seed=1, settings=EXTRACTION)
    assert len(session.rounds) == 2 and session.final.issues == ()
    assert 'about a week" or "a week" is 5' in fake.requests[0].messages[0].content
    assert "is not a short name" in fake.requests[1].messages[-1].content
    value = session.final.response.value
    assert value is not None
    draft = draft_definition(value, date(2026, 11, 9), "pl")
    login, sms = draft.tasks
    assert login.name == "Logowanie i uprawnienia" and login.description == long
    assert sms.optional and not login.optional


def test_an_absence_of_somebody_the_message_does_not_name_is_left_to_check() -> None:
    """The WP12 runs: qwen2.5:7b gave "Marek is on leave" to Tomasz; such an absence is shown
    unticked, with a note, since the message does not name its person."""
    from sentinel.app.llm import named_in

    assert named_in("Tomasz Nowak", "Tomka nie będzie do piątku")
    assert named_in("Ania Nowak", "Ani nie będzie, logowanie potrwa dłużej.")
    assert named_in("Filip Wójcik", "Filip jest na urlopie")
    assert not named_in("Tomasz Nowak", "Marek jest na urlopie do środy")
