"""A check-in message for the AI (WP11, WP12, WP14). WP14: the owner's rehearsal of the
usability test gave one wrong absence for a report of three facts, so the application's reader
now asks for calendar dates with their words and settles them in code (spec section 11.3,
v2.3.0), reads progress, finishes and starts too, and asks where it cannot decide."""

import json
from datetime import date
from pathlib import Path

import pytest
from app_cases import checked_in, planned, small

from sentinel.app.date_words import read_words, resolve, return_after
from sentinel.app.io import definition_from_csv
from sentinel.app.live import LiveProject
from sentinel.app.message_reader import (
    MessageContext,
    draft,
    read,
    split_clauses,
    withheld_issue,
)
from sentinel.app.models import Person, Settings
from sentinel.llm import FakeLlmClient, LlmCache
from sentinel.llm.core import ErrorDetail

ROOT = Path(__file__).resolve().parents[1]
OWNER = (
    '„Warsztat z klientem" skończył się wczoraj, we wtorek 3 listopada.\n'
    '„Baza danych i API" trwa, zrobiono około 15 %.\n'
    "Bartosz Kowalski od jutra jest nieobecny i wraca w poniedziałek 16 listopada."
)
WEDNESDAY = date(2026, 11, 4)  # the usability test's "today"


def usability() -> LiveProject:
    """The usability test's project as a tester makes it (docs/usability), planned."""
    folder = ROOT / "docs" / "usability"
    lines = (folder / "zespol-testowy.txt").read_text("utf-8").splitlines()
    team = tuple(
        Person(key=f"P{i}", name=name.strip(), role=role.strip())
        for i, (name, role) in enumerate((line.split(",", 1) for line in lines if line), 1)
    )
    definition = definition_from_csv(
        (folder / "projekt-testowy.csv").read_bytes(),
        None,
        name="P1 Aplikacja rezerwacji wizyt",
        start=date(2026, 11, 2),
        deadline=date(2026, 12, 4),
        settings=Settings(language="pl"),
    )
    return planned(definition.model_copy(update={"team": team}))


def answer(*items: dict[str, object], **rest: object) -> str:
    return json.dumps({"items": list(items), **rest}, ensure_ascii=False)


def day(value: str, words: str) -> dict[str, str]:
    return {"day": value, "words": words}


def review(project: LiveProject, text: str, *answers: str, when: date = WEDNESDAY) -> object:
    context = MessageContext(project, when, text)
    client = FakeLlmClient(list(answers))
    return draft(read(client, context, seed=1), context)


def test_the_owners_message_gives_its_three_items_from_the_recorded_answer() -> None:
    """Acceptance 1 of WP14 with gpt-oss-120b's recorded answer: the workshop done on Tue 3 Nov,
    the API in progress at 15 %, Bartosz away from Thu 5 Nov and back on Mon 16 Nov."""
    recorded = json.loads((ROOT / "tests" / "fixtures" / "owner_message_answer.json").read_text())
    found = review(usability(), OWNER, json.dumps(recorded["answer"], ensure_ascii=False))
    assert [(t.task, t.status, t.finish, t.percent) for t in found.tasks] == [
        ("T1", "done", date(2026, 11, 3), None),
        ("T3", "in_progress", None, 15),
    ]
    [away] = found.absences
    assert (away.person, away.first_day, away.return_date) == (
        "P2",
        date(2026, 11, 5),
        date(2026, 11, 16),
    )
    assert found.questions == () and found.unparsed == () and found.doubtful == ()


def test_code_settles_the_dates_whatever_day_the_model_counted() -> None:
    """The rehearsal's fault: the model counted working days across 11 November. Its days
    no longer matter where the words fix the date: "od jutra" is the next working day after the
    report, "wraca w poniedziałek 16 listopada" is 16 November, "wczoraj" is 3 November."""
    found = review(
        usability(),
        OWNER,
        answer(
            {
                "type": "done",
                "clause": 1,
                "task": "Warsztat z klientem",
                "day": day("2026-11-02", "wczoraj, we wtorek 3 listopada"),
            },
            {
                "type": "absence",
                "clause": 3,
                "person": 1,
                "since": day("2026-11-04", "od jutra"),
                "back": day("2026-11-18", "wraca w poniedziałek 16 listopada"),
            },
        ),
    )
    assert found.tasks[0].finish == date(2026, 11, 3)
    assert (found.absences[0].first_day, found.absences[0].return_date) == (
        date(2026, 11, 5),
        date(2026, 11, 16),
    )
    friday = MessageContext(usability(), date(2026, 11, 6), "Ewa od jutra nie pracuje.")
    tomorrow = read_words("od jutra")
    assert resolve(tomorrow, None, "since", friday.when, friday.calendar).day == date(2026, 11, 9)


def test_until_a_weekday_is_away_through_it_and_back_on_a_weekday_is_back_that_day() -> None:
    """Spec section 11.3 (v2.1.5, v2.3.0): "do piątku" is back on Monday, "wraca w piątek" on
    Friday; "do środy 11 listopada", a holiday, is back on Thursday 12 November."""
    project = usability()
    until = review(
        project,
        "Bartosz od jutra do piątku ma urlop.",
        answer(
            {
                "type": "absence",
                "clause": 1,
                "person": 1,
                "since": day("2026-11-05", "od jutra"),
                "until": day("2026-11-06", "do piątku"),
            }
        ),
    )
    back = review(
        project,
        "Ewa wraca w piątek, od jutra jej nie ma.",
        answer(
            {
                "type": "absence",
                "clause": 1,
                "person": 4,
                "since": day("2026-11-05", "od jutra"),
                "back": day("2026-11-06", "wraca w piątek"),
            }
        ),
    )
    assert until.absences[0].return_date == date(2026, 11, 9)
    assert back.absences[0].return_date == date(2026, 11, 6)
    calendar = project.calendar
    assert return_after(calendar, date(2026, 11, 11)) == date(2026, 11, 12)
    assert return_after(calendar, date(2027, 1, 3)) == date(2027, 1, 4)


def test_a_contradicting_weekday_a_holiday_and_two_possible_days_are_questions() -> None:
    """WP14: a mismatch or a day that is not a working day is asked, not shifted silently; so
    is "od poniedziałku" in the present tense, which names the Monday past or the next one."""
    project = usability()
    mismatch = review(
        project,
        "Warsztat z klientem skończyliśmy w poniedziałek 3 listopada.",
        answer(
            {
                "type": "done",
                "clause": 1,
                "task": "Warsztat z klientem",
                "day": day("2026-11-03", "w poniedziałek 3 listopada"),
            }
        ),
    )
    [question] = mismatch.questions
    assert (question.kind, question.task, question.problem, question.weekday) == (
        "date",
        "T1",
        "mismatch",
        0,
    )
    assert [t.finish for t in question.tasks] == [date(2026, 11, 2), date(2026, 11, 3)]
    assert mismatch.tasks == ()
    holiday = review(
        project,
        "Dawid od jutra choruje, wraca 11 listopada.",
        answer(
            {
                "type": "absence",
                "clause": 1,
                "person": 3,
                "since": day("2026-11-05", "od jutra"),
                "back": day("2026-11-11", "wraca 11 listopada"),
            }
        ),
    )
    [question] = holiday.questions
    assert (question.problem, question.said) == ("non_working", date(2026, 11, 11))
    assert [a.return_date for a in question.absences] == [date(2026, 11, 12)]
    assert holiday.absences == ()
    present = review(
        project,
        "Celina od poniedziałku jest na zwolnieniu.",
        answer(
            {
                "type": "absence",
                "clause": 1,
                "person": 2,
                "since": day("2026-11-09", "od poniedziałku"),
            }
        ),
    )
    assert [a.first_day for a in present.questions[0].absences] == [
        date(2026, 11, 2),
        date(2026, 11, 9),
    ]
    future = review(
        project,
        "Celina od poniedziałku będzie na urlopie.",
        answer(
            {
                "type": "absence",
                "clause": 1,
                "person": 2,
                "since": day("2026-11-02", "od poniedziałku"),
            }
        ),
    )
    assert future.questions == () and future.absences[0].first_day == date(2026, 11, 9)


def test_task_words_match_tolerantly_and_words_that_fit_several_tasks_ask() -> None:
    """Quotes, case and Polish inflection ("Z Bazy danych i API"); "testy" of the showcase fits
    two tasks, so the review asks which one grew."""
    from sentinel.app import showcase
    from sentinel.app.live import build_model

    project = usability()
    context = MessageContext(
        project, WEDNESDAY, "Z Bazy danych i API zrobiono połowę, „baza danych i api” też."
    )
    assert context.match("Bazy danych i API") == ["T3"] == context.match("„baza danych i api”")
    shop = LiveProject(showcase.definition("pl"))
    from sentinel.app import planning

    shop.set_baseline(planning.baseline_plan(build_model(shop.definition)))
    found = review(
        shop,
        "Testy potrwają 3 dni dłużej, a interfejs katalogu jest w 20 %.",
        answer(
            {"type": "more_work", "clause": 1, "task": "Testy integracyjne", "extra_days": 3},
            {"type": "progress", "clause": 2, "task": "interfejs katalogu", "percent": 20},
        ),
    )
    [question] = found.questions  # "integracyjne" is not in the message: only "testy" counts
    assert question.kind == "ambiguous_task" and question.candidates == ("T9", "T10")
    assert [g.extra_days for g in question.increases] == [3, 3]
    assert [(t.task, t.percent) for t in found.tasks] == [("T6", 20)]


def test_a_date_with_other_words_is_never_cached_and_is_asked_for_again(tmp_path: Path) -> None:
    """Invariant 7: the words of a date are date words only, so a reason ("choruje") cannot
    reach the answer the cache keeps; the answer is withheld and its repair round asked."""
    cache = LlmCache(tmp_path / "cache.jsonl", store_prompts=False)
    text = "Dawid od jutra choruje, wraca w piątek."
    bad = answer(
        {
            "type": "absence",
            "clause": 1,
            "person": 3,
            "since": day("2026-11-05", "od jutra choruje"),
            "back": day("2026-11-06", "wraca w piątek"),
        }
    )
    good = bad.replace("od jutra choruje", "od jutra")
    context = MessageContext(usability(), WEDNESDAY, text)
    reading = read(FakeLlmClient([bad, good], cache=cache), context, seed=1)
    assert reading.rounds == 1 and reading.issues == ()
    assert "choruje" not in (tmp_path / "cache.jsonl").read_text("utf-8")
    assert draft(reading, context).absences[0].return_date == date(2026, 11, 6)
    hint = withheld_issue(ErrorDetail("items[0]", "phrase_words", "phrase_words")).message
    assert hint.startswith('items[0] has the issue "phrase words"; "words" holds only')


def test_nothing_in_a_message_is_dropped_silently() -> None:
    """WP12 (B6), WP14: the clauses that gave nothing are listed; a person not in the team is
    asked about with the dates of the absence; the answer holds clause numbers, date words and
    task words only, never another word of the message (invariant 7)."""
    text = "Marek jest chory do piątku, a projekt ekranów zacznie się jutro. Spotkanie w piątek."
    assert split_clauses(text, "pl") == (
        "Marek jest chory do piątku",
        "projekt ekranów zacznie się jutro.",
        "Spotkanie w piątek.",
    )
    found = review(
        usability(),
        text,
        answer(
            {
                "type": "progress",
                "clause": 2,
                "task": "projekt ekranów",
                "started": day("2026-11-05", "jutro"),
            },
            unparsed=[3],
            questions=[
                {"kind": "unknown_person", "clause": 1, "until": day("2026-11-06", "do piątku")}
            ],
        ),
    )
    [question] = found.questions
    assert (question.first_day, question.return_date) == (WEDNESDAY, date(2026, 11, 9))
    assert found.unparsed == (2, 3)  # a start tomorrow is no report of today
    assert "Marek" not in found.model_dump_json() and "chory" not in found.model_dump_json()


def test_the_context_lists_the_report_date_the_calendar_and_the_team() -> None:
    """WP14: the report date with its weekday and the weeks around it, holidays marked, so that
    the model names dates and never counts working days."""
    context = MessageContext(usability(), WEDNESDAY, OWNER)
    text = context.render()
    assert "Report date: Wed 2026-11-04;" in text
    assert "Wed 2026-11-11 (holiday)" in text and "Wed 2026-11-04 (report date)" in text
    assert "Thu 2026-12-24 (holiday)" in text and "Mon 2026-10-19" in text
    assert "- 1 Bartosz Kowalski (Programista)" in text
    assert '- "Baza danych i API": not started' in text
    assert "[3] Bartosz Kowalski od jutra jest nieobecny" in text


@pytest.mark.parametrize(
    ("words", "role", "report", "given", "expected"),
    [
        ("do Wigilii", "until", "2026-12-18", "2026-12-24", "2026-12-24"),
        ("od jutra", "since", "2026-12-23", "2026-12-24", "2026-12-28"),
        ("do 3 stycznia", "until", "2026-12-23", "2027-01-03", "2027-01-03"),
        ("w piątek", "done", "2026-11-30", None, "2026-11-27"),
        ("od 23", "since", "2026-11-20", "2026-11-23", "2026-11-23"),
    ],
)
def test_dates_across_christmas_the_new_year_and_days_without_a_month(
    words: str, role: str, report: str, given: str | None, expected: str
) -> None:
    calendar = usability().calendar
    found = resolve(
        read_words(words),
        None if given is None else date.fromisoformat(given),
        role,  # type: ignore[arg-type]
        date.fromisoformat(report),
        calendar,
    )
    assert found.day == date.fromisoformat(expected) and found.problem is None


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
        service.client = lambda session=None, fake=fake: fake  # type: ignore[method-assign]
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
    from sentinel.app.message_reader import named_in

    assert named_in("Tomasz Nowak", "Tomka nie będzie do piątku")
    assert named_in("Ania Nowak", "Ani nie będzie, logowanie potrwa dłużej.")
    assert named_in("Filip Wójcik", "Filip jest na urlopie")
    assert not named_in("Tomasz Nowak", "Marek jest na urlopie do środy")
