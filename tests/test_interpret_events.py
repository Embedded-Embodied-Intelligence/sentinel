"""Role 1 of the interpretation layer (spec section 10.2): generated team messages, the template
parser, validation, privacy, application to the observation and the repair loop."""

import json
from collections.abc import Callable

import numpy as np
import pytest
from test_sentinel import lively_observations

from sentinel.interpret.events import (
    REASON_WORDS,
    REASONS,
    AbsenceEvent,
    Context,
    MessageEvents,
    NewActivityEvent,
    ParseSettings,
    TeamMessage,
    WorkIncreaseEvent,
    apply_events,
    compare_events,
    leaks,
    parse,
    read_answer,
    same_observation,
)
from sentinel.interpret.messages import MessageSettings, generate, read_message
from sentinel.interpret.team import names_of, next_week, next_weekday, roster
from sentinel.llm import FakeLlmClient, backend_schema
from sentinel.model import ProjectInstance
from sentinel.simulation.state import PAUSED, RUNNING, UNSTARTED

Builder = Callable[..., ProjectInstance]


@pytest.fixture
def contexts(build: Builder) -> list[Context]:
    """Contexts of epoch observations of NoReaction runs with frequent absences."""
    observations = lively_observations(build, count=3)
    found = []
    for observation in observations[:: max(1, len(observations) // 12)][:12]:
        members = roster(observation.instance, 5)
        found.append(Context(observation, names_of(observation, 5), members))
    return found


def test_the_calendar_names_days_forward() -> None:
    assert next_weekday(3, 0) == 5  # Thursday (day 3) to Monday
    assert next_weekday(5, 0) == 10  # Monday to the next Monday, a week later
    assert next_weekday(6, 4) == 9  # Tuesday to Friday
    assert next_week(9) == 10 and next_week(10) == 15


def test_the_message_generator_round_trips_through_the_template_parser(
    contexts: list[Context],
) -> None:
    """A template parser recovers every message's events exactly, and the true events are valid
    in their context; every kind of fact, the self form and multi-fact messages occur."""
    rng = np.random.default_rng(2026)
    kinds: set[str] = set()
    forms = {"multi": 0, "self": 0, "reason": 0}
    for _ in range(40):
        for context in contexts:
            generated = generate(context, rng, MessageSettings())
            assert read_message(generated.message, context) == generated.events
            data = {"events": [e.model_dump() for e in generated.events]}
            reading = read_answer(data, context)
            assert reading.valid, reading.issues
            assert compare_events(generated.events, reading.events).exact
            kinds |= set(generated.facts)
            forms["multi"] += len(generated.facts) > 1
            forms["reason"] += bool(generated.reasons)
            forms["self"] += any(
                isinstance(e, AbsenceEvent) and e.worker == generated.message.author
                for e in generated.events
            )
    assert kinds == {"absence", "work_increase", "new_activity", "noise"}
    assert all(count > 0 for count in forms.values()), forms


def test_generation_is_deterministic_per_seed(contexts: list[Context]) -> None:
    first = [generate(contexts[0], np.random.default_rng(7), MessageSettings()) for _ in range(3)]
    again = [generate(contexts[0], np.random.default_rng(7), MessageSettings()) for _ in range(3)]
    assert first == again


def test_no_reason_word_reaches_a_parsed_event(contexts: list[Context]) -> None:
    """The output schema has no field for a reason; an answer that adds one is rejected and
    repaired, and no accepted event of any message contains a word of the generator's reasons."""
    schema = json.dumps(backend_schema(MessageEvents))
    assert "reason" not in schema
    rng = np.random.default_rng(11)
    settings = MessageSettings(reason_share=1.0)
    checked = 0
    for _ in range(8):
        for context in contexts:
            generated = generate(context, rng, settings)
            truth = [e.model_dump() for e in generated.events]
            smuggled = [
                {**e, "reason": generated.reasons[0]} if e["type"] == "absence" else e
                for e in truth
            ]
            client = FakeLlmClient(
                [json.dumps({"events": smuggled}), json.dumps({"events": truth})]
            )
            session = parse(
                client,
                generated.message,
                context,
                seed=1,
                settings=ParseSettings(max_tokens=512),
            )
            accepted = session.final.reading.events
            assert leaks([e.model_dump() for e in accepted]) == 0
            if generated.reasons and any(e["type"] == "absence" for e in truth):
                assert session.single_shot.reading.issues  # the "reason" field is rejected
                assert leaks(session.single_shot.response.parsed) > 0  # and was seen in the raw
                checked += 1
            assert compare_events(generated.events, accepted).exact
    assert checked >= 5
    assert all(any(word in reason for word in REASON_WORDS) for reason in REASONS)


def test_the_leak_counter_finds_a_reason_in_any_string() -> None:
    answer = {"events": [{"type": "new_activity", "name": "Cover Ada's flu week", "crew": {}}]}
    assert leaks(answer) == 1
    assert leaks({"events": [{"type": "absence", "worker": 3, "return_day": 9}]}) == 0


def _context_with(contexts: list[Context], status: str) -> Context:
    return next(c for c in contexts if status in c.observation.status)


def test_validation_lists_every_issue_type(contexts: list[Context]) -> None:
    context = next(
        c
        for c in contexts
        if RUNNING in c.observation.status
        and UNSTARTED in c.observation.status
        and not all(c.observation.present[: len(c.roster)])
    )
    observation, t = context.observation, context.day
    present = next(m.worker for m in context.roster if observation.present[m.worker])
    absent = next(m.worker for m in context.roster if not observation.present[m.worker])
    running = next(j for j in context.names if observation.status[j] == RUNNING)
    unstarted = [j for j in context.names if observation.status[j] == UNSTARTED]
    not_running = next(j for j in context.names if observation.status[j] != RUNNING)
    role = context.roles[0]
    events = [
        {"type": "absence", "worker": 999, "return_day": None},
        {"type": "absence", "worker": absent, "return_day": t + 2},
        {"type": "absence", "worker": present, "return_day": t},
        {"type": "work_increase", "activity": 999, "factor": 1.5},
        {"type": "work_increase", "activity": not_running, "factor": 1.5},
        {"type": "work_increase", "activity": running, "factor": 0.5},
        {"type": "absence", "worker": present, "return_day": t + 1},
        {"type": "absence", "worker": present, "return_day": t + 2},
        {
            "type": "new_activity",
            "name": context.names[running],
            "duration": 0,
            "crew": {"designer": 1, role: 99},
            "after": unstarted[0],
            "before": unstarted[0],
        },
        {"type": "vacation", "worker": present},
        {"type": "absence", "worker": present},
        {"type": "absence", "worker": present, "return_day": None, "reason": "flu"},
    ]
    reading = read_answer({"events": events}, context)
    kinds = {issue.kind for issue in reading.issues}
    assert kinds == {
        "unknown_worker",
        "already_absent",
        "impossible_day",
        "unknown_activity",
        "not_running",
        "factor_below_one",
        "duplicate",
        "name_in_use",
        "non_positive_duration",
        "unknown_role",
        "crew_above_capacity",
        "invalid_placement",
        "unknown_type",
        "missing_field",
        "invalid_field",
    }
    assert reading.events == (AbsenceEvent(type="absence", worker=present, return_day=t + 1),)
    assert all("flu" not in issue.message for issue in reading.issues)
    assert read_answer([], context).issues[0].kind == "invalid_field"


def test_applied_events_change_the_observation_as_the_engine_would(
    contexts: list[Context],
) -> None:
    context = _context_with(contexts, RUNNING)
    observation, t = context.observation, context.day
    j = next(
        j for j in context.names if observation.status[j] == RUNNING and observation.assigned[j]
    )
    crew = [w for w in observation.assigned[j] if observation.present[w]]
    unstarted = next((k for k in context.names if observation.status[k] == UNSTARTED), None)
    events = [
        *(AbsenceEvent(type="absence", worker=w, return_day=t + 3) for w in crew),
        WorkIncreaseEvent(type="work_increase", activity=j, factor=1.5),
        NewActivityEvent(
            type="new_activity",
            name="Write release notes",
            duration=2,
            crew={context.roles[0]: 1},
            after=j,
            before=unstarted,
        ),
    ]
    after = apply_events(context, events)
    assert after.status[j] == PAUSED
    assert all(not after.present[w] and after.announced[w] == 3 for w in crew)
    assert after.work_increases[-1] == (j, observation.work_done[j], 1.5)
    new = len(observation.status)
    assert after.status[new] == UNSTARTED and after.inserted[-1].predecessor == j
    assert after.plan[new] >= t + 1
    assert same_observation(after, apply_events(context, list(reversed(events))))
    assert not same_observation(after, apply_events(context, events[:-1]))
    unknown = apply_events(context, [AbsenceEvent(type="absence", worker=crew[0], return_day=None)])
    assert unknown.announced[crew[0]] == 1


def test_the_repair_loop_fixes_a_caught_mistake_and_stops(contexts: list[Context]) -> None:
    context = contexts[0]
    worker = next(m.worker for m in context.roster if context.observation.present[m.worker])
    message = TeamMessage(day=context.day, author=worker, text="I can't come in today.")
    good = {"events": [{"type": "absence", "worker": worker, "return_day": None}]}
    bad = {"events": [{"type": "absence", "worker": 999, "return_day": None}]}
    client = FakeLlmClient([json.dumps(bad), "not json", json.dumps(good)])
    session = parse(client, message, context, seed=3, settings=ParseSettings(max_tokens=256))
    assert [r.reading.valid for r in session.rounds] == [False, False, True]
    assert session.rounds[1].reading.issues[0].kind == "invalid_json"
    assert "999" in client.requests[1].messages[-1].content
    never = FakeLlmClient(lambda messages: json.dumps(bad))
    stuck = parse(never, message, context, seed=3, settings=ParseSettings(max_tokens=256))
    assert stuck.repair_rounds == 3 and not stuck.final.reading.valid


def test_observations_differ_only_within_the_factor_tolerance(contexts: list[Context]) -> None:
    context = _context_with(contexts, RUNNING)
    j = next(j for j in context.names if context.observation.status[j] == RUNNING)
    a = apply_events(context, [WorkIncreaseEvent(type="work_increase", activity=j, factor=1.57)])
    b = apply_events(context, [WorkIncreaseEvent(type="work_increase", activity=j, factor=1.58)])
    c = apply_events(context, [WorkIncreaseEvent(type="work_increase", activity=j, factor=1.6)])
    assert same_observation(a, b) and not same_observation(a, c)
