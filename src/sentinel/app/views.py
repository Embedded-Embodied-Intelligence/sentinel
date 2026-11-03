"""What the API shows of a project, in the user's language (spec section 11): every day as a
calendar date, tasks and people by name, recommendations as plain-language actions with their
effect, issues as messages. The views are pydantic models, so the JSON API and the HTML pages
of WP9b render the same data.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sentinel.agent.decide import CandidateRecord
from sentinel.app.calendar import WorkCalendar
from sentinel.app.events import LiveState, LlmExplanation, RecommendationEntry, Source
from sentinel.app.live import AppliedAction, Issue, LiveProject, Tracked, validate_definition
from sentinel.app.messages import render
from sentinel.app.models import Language, ProjectDefinition
from sentinel.app.planning import (
    ForecastResult,
    Impact,
    ThreatList,
    Tie,
    residual_plan,
    sentinel_params,
    tie_kind,
)
from sentinel.dashboard.explain import template_explanation
from sentinel.policies.base import LEVELS, Decision, Descope, Overtime, Reseq, Shift, Subst
from sentinel.simulation.state import PAUSED, RUNNING, Observation


class View(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IssueView(View):
    code: str
    message: str
    where: str | None
    severity: Literal["error", "warning"]


def issue_views(issues: Sequence[Issue], language: Language) -> list[IssueView]:
    return [
        IssueView(
            code=i.code,
            message=render(i.code, language, i.values),
            where=i.where,
            severity=i.severity,
        )
        for i in issues
    ]


ProgressState = Literal["not_started", "in_progress", "paused", "done", "removed"]


class TaskView(View):
    """A task as the manager sees it: its definition, its progress and its plan; the planned
    dates are those of the current plan (`residual_plan`, B2 of the WP12 test), the original
    plan's are kept apart."""

    key: str
    name: str
    duration: int
    crew: dict[str, int]
    predecessors: list[str]
    optional: bool
    added: bool
    state: ProgressState
    state_text: str
    percent: float | None
    start: date | None
    finish: date | None
    planned_start: date | None
    planned_finish: date | None
    crew_names: list[str]
    late: bool
    expected_finish: date | None = None  # of a started task, in the current plan (v2.2.0)
    due: date | None = None  # the planned start a late task has missed
    baseline_start: date | None = None  # in the original plan
    baseline_finish: date | None = None


class AbsenceView(View):
    first_day: date
    return_date: date | None


class PersonView(View):
    key: str
    name: str
    role: str
    temporary: bool
    absent: bool
    absences: list[AbsenceView]
    hired_until: date | None


class BaselineView(View):
    makespan: int
    finish: date
    method: str
    status: str


class CheckinView(View):
    date: date
    day: int


class OutcomeView(View):
    """A candidate's effect: P(on time), the expected finish date (of the mean makespan), the
    most likely finish and the bad case (the 50 and 90 % quantiles, as the overview shows them;
    None for a recommendation stored before v2.2.0), expected cost and overrun."""

    p_on_time: float
    expected_finish: date | None
    tardiness: float
    expected_cost: float
    overrun: float
    rollouts: int
    likely_finish: date | None = None
    bad_finish: date | None = None


class ChangeView(View):
    task: str
    name: str
    old: date
    new: date


class AlternativeView(View):
    """An option compared with the recommended action; `dropped`: racing set it aside early in
    the deliberation (spec section 6)."""

    label: str
    title: str
    p_on_time: float
    tardiness: float
    expected_cost: float
    dropped: bool
    runner_up: bool = False


class ExplanationView(View):
    """An explanation (spec section 10.4): the template's, or an LLM's with its badge."""

    text: str
    source: Literal["template", "llm"]
    model: str | None = None
    badge: Literal["template", "faithful", "unfaithful", "invalid"] = "template"
    facts_right: int = 0
    facts: int = 0
    hallucinated: int = 0


class RecommendationView(View):
    """A recommendation (spec section 11.5): the action in words, its effect against no change,
    why it needs approval ("people", "money", "scope", "plan"), the alternatives and whether its
    automatic plan change can be undone. `compared`: its figures come from the comparison on
    the forecast's simulated futures (v2.0.2), not from the deliberation's own; `options`: the
    number of candidates Sentinel weighed; `tie`: an alternative shown has a higher chance than
    the action, so the page says why in one sentence (v2.0.4)."""

    seq: int
    day: int
    as_of: date
    date: date
    status: str
    status_text: str
    label: str
    kind: str
    title: str
    acts: bool
    level: int
    needs_approval: bool
    approval_reasons: list[str]
    can_undo: bool
    urgency: float | None
    can_wait: bool
    reason: str
    reason_text: str
    with_action: OutcomeView | None
    without: OutcomeView | None
    changes: list[ChangeView]
    alternatives: list[AlternativeView]
    compared: bool = False
    options: int = 0
    budget: float | None = None
    tie: Tie | None = None
    explanation: ExplanationView
    llm_explanation: ExplanationView | None
    discarded: str | None


class ProjectSummary(View):
    id: str
    kind: Literal["live", "simulator"]
    name: str
    created: datetime
    updated: datetime


class ProjectView(View):
    """A live project (spec section 11) for the API and the pages."""

    id: str
    kind: Literal["live"] = "live"
    name: str
    seq: int
    source: Source
    definition: ProjectDefinition
    issues: list[IssueView]
    has_plan: bool
    tracking: bool
    finished: bool
    day: int
    as_of: date
    deadline: date | None
    budget: float | None
    cost_so_far: float | None
    person_days: bool = True  # every daily cost is the default cost unit: a person-day (11.2)
    baseline: BaselineView | None
    tasks: list[TaskView]
    people: list[PersonView]
    checkins: list[CheckinView]
    recommendations: list[RecommendationView]
    open_recommendation: int | None


class DriverView(View):
    task: str
    name: str
    sensitivity: float


class ForecastView(View):
    """A forecast as shown (spec section 11.4); `drivers` is None until the list is calculated,
    and `threat_rollouts` the futures it reads."""

    day: int
    as_of: date
    rollouts: int
    p_on_time: float | None
    deadline: date | None
    p10: date
    p50: date
    p90: date
    mean: float
    drivers: list[DriverView] | None
    threat_rollouts: int | None = None
    late: int = 0
    expected_cost: float | None = None
    budget: float | None = None
    p_within_budget: float | None = None


class ForecastSummary(View):
    """The forecast now and the chance of meeting the deadline before the latest check-in (the
    trend shown with it; None without an earlier forecastable state or a deadline); after an
    approval whose figures it does not show, what changed since the recommendation ("deadline",
    "budget", "settings" or "replanned", spec section 11.5)."""

    forecast: ForecastView
    previous_p: float | None
    promise_note: str | None = None  # why it differs from an approved card's figures (v2.2.0)


# --------------------------------------------------------------------------- builders


def project_view(
    project_id: str, state: LiveState, language: Language, name: str | None = None
) -> ProjectView:
    project = state.project
    definition = project.definition
    calendar = project.calendar
    issues = validate_definition(definition)
    observation = None
    if project.baseline is not None and not [i for i in issues if i.severity == "error"]:
        observation = project.observation()
    model = project.require_model() if observation is not None else None
    baseline = project.baseline
    return ProjectView(
        id=project_id,
        name=name or definition.name,
        seq=state.seq,
        source=state.source,
        definition=definition,
        issues=issue_views(issues, language),
        has_plan=baseline is not None,
        tracking=project.tracking,
        finished=project.finished,
        day=project.day,
        as_of=calendar.date_of(project.day),
        deadline=definition.deadline,
        budget=None if model is None else model.budget,
        cost_so_far=None if observation is None else observation.cost,
        person_days=all(cost.daily_cost == 1.0 for cost in definition.roles),
        baseline=None
        if baseline is None
        else BaselineView(
            makespan=baseline.makespan,
            finish=calendar.finish_date(baseline.makespan),
            method=baseline.method,
            status=baseline.status,
        ),
        tasks=task_views(project, observation, language),
        people=person_views(project, observation, language),
        checkins=[CheckinView(date=d, day=t) for d, t in project.checkins],
        recommendations=[
            recommendation_view(project, r, language, state.can_undo(r))
            for r in state.recommendations
        ],
        open_recommendation=None if state.open is None else state.open.seq,
    )


def task_views(
    project: LiveProject, observation: Observation | None, language: Language
) -> list[TaskView]:
    calendar = project.calendar
    definition = project.definition
    names = person_names(project, language)
    rows: list[TaskView] = []
    if observation is None or not project.tasks:
        for task in definition.tasks:
            rows.append(
                TaskView(
                    key=task.key,
                    name=task.name,
                    duration=task.duration,
                    crew=dict(task.crew),
                    predecessors=list(task.predecessors),
                    optional=task.optional,
                    added=False,
                    state="not_started",
                    state_text=render("progress_not_started", language),
                    percent=None,
                    start=None,
                    finish=None,
                    planned_start=None,
                    planned_finish=None,
                    crew_names=[],
                    late=False,
                )
            )
        return rows
    nodes = project.nodes()
    ids = project.activity_ids()
    by_key = {task.key: task for task in definition.tasks}
    added = {task.key: task for task in project.inserted}
    current = residual_plan(project)
    original = {} if project.baseline is None else project.baseline.starts
    for key, tracked in project.tasks.items():
        node = nodes[key]
        j = ids[key]
        status = observation.status[j]
        state: ProgressState
        if status == RUNNING:
            state = "in_progress"
        elif status == PAUSED:
            state = "paused"
        elif status == "done":
            state = "done"
        elif status == "removed":
            state = "removed"
        else:
            state = "not_started"
        factors = 1.0
        for shock in project.shocks:
            if shock.task == key:
                factors *= shock.factor
        percent = None
        if state in ("in_progress", "paused"):
            total = node.duration * factors * node.unit
            percent = round(100 * tracked.work / total, 1)
        definition_task = by_key.get(key)
        crew = dict(definition_task.crew) if definition_task else dict(added[key].crew)
        predecessors = list(node.predecessors)
        planned = current.starts.get(key) if state == "not_started" else None
        ends = current.finishes.get(key) if state in ("in_progress", "paused") else None
        first = original.get(key)
        late = state == "not_started" and tracked.planned < observation.day
        rows.append(
            TaskView(
                key=key,
                name=node.name,
                duration=node.duration,
                crew=crew,
                predecessors=predecessors,
                optional=node.optional,
                added=key in added,
                state=state,
                state_text=render(f"progress_{state}", language),
                percent=percent,
                start=None if tracked.start is None else calendar.date_of(tracked.start),
                finish=None if tracked.finish is None else calendar.finish_date(tracked.finish),
                planned_start=None if planned is None else calendar.date_of(planned),
                planned_finish=None
                if planned is None
                else calendar.finish_date(planned + node.duration),
                crew_names=[names.get(member, member) for member in tracked.crew],
                late=late,
                due=calendar.date_of(tracked.planned) if late else None,
                expected_finish=None if ends is None else calendar.finish_date(ends),
                baseline_start=None if first is None else calendar.date_of(first),
                baseline_finish=None
                if first is None
                else calendar.finish_date(first + node.duration),
            )
        )
    return rows


def person_names(project: LiveProject, language: Language | None = None) -> dict[str, str]:
    """The name of every person key; temporary workers as stored ("Temporary <role> n"), or in
    `language` (spec section 11.7)."""
    names = {p.key: p.name for p in project.definition.team}
    if language is None or not project.temps:
        names.update({temp.key: temp.name for temp in project.temps})
        return names
    role_names = project.require_model().role_names
    numbers: dict[int, int] = {}
    for temp in project.temps:
        numbers[temp.role] = numbers.get(temp.role, 0) + 1
        values = {"role": role_names[temp.role], "number": numbers[temp.role]}
        names[temp.key] = render("temporary_person", language, values)
    return names


def person_views(
    project: LiveProject, observation: Observation | None, language: Language | None = None
) -> list[PersonView]:
    calendar = project.calendar
    rows = []
    for w, person in enumerate(project.definition.team):
        absences = [
            AbsenceView(
                first_day=calendar.date_of(a.start),
                return_date=None if a.back is None else calendar.date_of(a.back),
            )
            for a in project.absences
            if a.person == person.key
        ]
        rows.append(
            PersonView(
                key=person.key,
                name=person.name,
                role=person.role,
                temporary=False,
                absent=observation is not None and not observation.present[w],
                absences=absences,
                hired_until=None,
            )
        )
    if project.temps:
        model = project.require_model()
        names = person_names(project, language)
        for temp in project.temps:
            rows.append(
                PersonView(
                    key=temp.key,
                    name=names[temp.key],
                    role=model.role_names[temp.role],
                    temporary=True,
                    absent=False,
                    absences=[],
                    hired_until=calendar.finish_date(temp.until),
                )
            )
    return rows


# --------------------------------------------------------------------------- recommendations


def describe(
    decision: Decision,
    kind: str,
    project: LiveProject,
    day: int,
    language: Language,
    applied: AppliedAction | None = None,
) -> str:
    """The action of a decision in the wording of spec section 11.7: a part per operation in
    operation order (a SUBST part per substitute, naming the absent member it replaces), the plan
    part last, later parts in lower case. `applied` is the action as the recommendation of `day`
    applied it, so that its own crew change is not taken for the crew it saw."""
    if not decision.operations:
        return render("action_noop", language)
    model = project.require_model()
    keys = {j: key for key, j in project.activity_ids().items()}
    nodes = project.nodes()
    names = person_names(project, language)
    parts = []
    plan_part = None
    for op in decision.operations:
        match op:
            case Subst():
                task = nodes[keys[op.activity]].name
                for worker, absent in replaced_members(project, op, day, applied):
                    values = {
                        "worker": names.get(worker, worker),
                        "absent": names.get(absent, absent) if absent is not None else "?",
                        "task": task,
                    }
                    parts.append(render("action_subst", language, values))
            case Overtime():
                code = "action_overtime_one" if op.workers == 1 else "action_overtime_many"
                hire = {"count": op.workers, "role": model.role_names[op.role], "days": op.days}
                parts.append(render(code, language, hire))
            case Descope():
                parts.append(
                    render("action_descope", language, {"task": nodes[keys[op.activity]].name})
                )
            case Shift():
                plan_part = render("action_shift", language)
            case Reseq():
                stable = kind.endswith("reseq_s")
                plan_part = render("action_reseq_s" if stable else "action_reseq_m", language)
    if plan_part is not None:
        parts.append(plan_part)
    first, *rest = parts
    return render("action_then", language).join([first, *(_lower_first(p) for p in rest)])


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def replaced_members(
    project: LiveProject, op: Subst, day: int, applied: AppliedAction | None = None
) -> list[tuple[str, str | None]]:
    """(substitute, replaced member) person keys of a SUBST on `day` (spec section 4): within a
    role, the substitutes in the order given replace the crew's absent members in increasing
    worker id order; None if no absent member of the substitute's role is found."""
    keys = {j: key for key, j in project.activity_ids().items()}
    workers = project.worker_keys()
    roles = project.worker_roles()
    index = {key: w for w, key in enumerate(workers)}
    tracked = project.tasks[keys[op.activity]]
    crew = _crew_before(tracked, day, applied)
    absent = sorted(
        index[member]
        for member in crew
        if member in index and project.absent(member, day) is not None
    )
    pairs: list[tuple[str, str | None]] = []
    for w in op.workers:
        if w >= len(workers):
            continue
        match = next((a for a in absent if roles[a] == roles[w]), None)
        if match is not None:
            absent.remove(match)
        pairs.append((workers[w], None if match is None else workers[match]))
    return pairs


def _crew_before(tracked: Tracked, day: int, applied: AppliedAction | None) -> tuple[str, ...]:
    """The crew of a task as a recommendation of `day` saw it: its crew history up to `day`,
    without the change of `applied`, the action that recommendation applied."""
    after = None if applied is None else applied.crews.get(tracked.key)
    crew: tuple[str, ...] = ()
    for first, members in tracked.crews:
        if first > day or (after is not None and first == day and members == after):
            break
        crew = members
    return crew or tracked.crew


APPROVAL_REASONS = {"subst": "people", "overtime": "money", "descope": "scope"}
# The model's labels in an AI text, in words (`plain_labels`); the AI writes English (spec 10).
ACTIVITY_NUMBER = re.compile(r"\bactivity (\d+)\b")
LABEL_WORDS = (
    (re.compile(r"(?<=[A-Z)])\+(?=[A-Z])"), " and "),
    (re.compile(r"\bNOOP\b"), "no change"),
    (re.compile(r"\bSHIFT\b"), "moving tasks"),
    (re.compile(r"\bRESEQ(?:-[MS])?\b"), "a new order of tasks"),
    (re.compile(r"\b(?:OVERTIME|OT)\b(?:\([^)]*\))?"), "extra people for a time"),
    (re.compile(r"\bSUBST-ALL\b"), "substitutes for everyone absent"),
    (re.compile(r"\bSUBST\((\d+)\)"), r"a substitute on activity \1"),
    (re.compile(r"\bSUBST\b"), "a substitute"),
    (re.compile(r"\bDESCOPE\((\d+)\)"), r"dropping activity \1"),
    (re.compile(r"\bDESCOPE\b"), "dropping an optional task"),
)


def approval_reasons(decision: Decision, autonomy: int) -> list[str]:
    """Why an action needs the manager's approval (spec sections 4 and 11.7): "people" (SUBST),
    "money" (OVERTIME), "scope" (DESCOPE) and "plan" (a plan change above the autonomy), each
    once, for the operations of level at least Lambda and DESCOPE."""
    reasons: list[str] = []
    for op in decision.operations:
        if op.kind == "noop" or (LEVELS[op.kind] < autonomy and op.kind != "descope"):
            continue
        reason = APPROVAL_REASONS.get(op.kind, "plan")
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _outcome(impact: Impact | None, calendar: WorkCalendar) -> OutcomeView | None:
    if impact is None:
        return None
    finish = likely = bad = None
    if impact.mean_makespan is not None:
        finish = calendar.finish_date(int(impact.mean_makespan + 0.5))
    if impact.quantiles is not None:
        likely, bad = (calendar.finish_date(q) for q in impact.quantiles[1:])
    return OutcomeView(
        p_on_time=impact.p_on_time,
        expected_finish=finish,
        tardiness=impact.tardiness,
        expected_cost=impact.mean_cost,
        overrun=impact.overrun,
        rollouts=impact.rollouts,
        likely_finish=likely,
        bad_finish=bad,
    )


def status_date(project: LiveProject, day: int) -> date:
    """The date whose end a recommendation of `day` reads: the date of its check-in (spec section
    11.1), or that day itself before any check-in (QA-19)."""
    reported = [dated for dated, t in project.checkins if t <= day]
    return reported[-1] if reported else project.calendar.date_of(day)


def recommendation_view(
    project: LiveProject,
    entry: RecommendationEntry,
    language: Language,
    can_undo: bool = False,
) -> RecommendationView:
    recommendation = entry.recommendation
    record = recommendation.record
    calendar = project.calendar
    chosen = recommendation.chosen
    decision = chosen.decision if chosen is not None else record.decision
    kind = chosen.kind if chosen is not None else "noop"
    params = sentinel_params(project)
    nodes = project.nodes()
    applied = entry.applied
    records = {c.label: c for c in record.candidates}

    def title(label: str) -> str:
        c = records.get(label)
        if c is None:
            return render("action_noop", language)
        return describe(c.decision, c.kind, project, recommendation.day, language, applied)

    if recommendation.comparison is not None:
        alternatives = [
            AlternativeView(
                label=i.label,
                title=title(i.label),
                p_on_time=i.p_on_time,
                tardiness=i.tardiness,
                expected_cost=i.mean_cost,
                dropped=i.label in records and records[i.label].dropped,
                runner_up=i.label == record.runner_up,
            )
            for i in recommendation.comparison.impacts
            if i.label != record.chosen
        ]
    else:  # stored before v2.0.2: the deliberation's own figures
        alternatives = [
            AlternativeView(
                label=c.label,
                title=title(c.label),
                p_on_time=c.p_on_time,
                tardiness=c.tardiness,
                expected_cost=c.mean_cost,
                dropped=c.dropped,
                runner_up=c.label == record.runner_up,
            )
            for c in _alternatives(record.candidates, record.chosen, record.runner_up)
        ]
    reason = record.reason
    needs_approval = recommendation.acts and params.needs_approval(decision)
    comparison = recommendation.comparison
    return RecommendationView(
        seq=entry.seq,
        day=recommendation.day,
        date=calendar.date_of(recommendation.day),
        as_of=status_date(project, recommendation.day),
        status=entry.status,
        status_text=render(f"status_{entry.status}", language),
        label=record.chosen,
        kind=kind,
        title=describe(decision, kind, project, recommendation.day, language, applied),
        acts=recommendation.acts,
        level=decision.level,
        needs_approval=needs_approval,
        approval_reasons=approval_reasons(decision, params.autonomy) if needs_approval else [],
        can_undo=can_undo,
        urgency=recommendation.urgency,
        can_wait=recommendation.urgency is not None and recommendation.urgency > params.tau_def,
        reason=reason,
        reason_text=render(f"reason_{reason}", language),
        with_action=_outcome(recommendation.impact(record.chosen), calendar),
        without=_outcome(recommendation.impact("NOOP"), calendar),
        changes=[
            ChangeView(
                task=change.task,
                name=nodes[change.task].name if change.task in nodes else change.task,
                old=calendar.date_of(change.old),
                new=calendar.date_of(change.new),
            )
            for change in recommendation.changes
        ],
        alternatives=alternatives,
        compared=recommendation.comparison is not None,
        options=len(record.candidates),
        budget=project.require_model().budget,
        tie=(
            tie_kind(record, comparison, params)
            if comparison is not None and comparison.decides
            else None
        ),
        explanation=ExplanationView(
            text=template_explanation(recommendation.as_shown, language).summary, source="template"
        ),
        llm_explanation=None if entry.explanation is None else plain_view(project, entry),
        discarded=entry.discarded,
    )


def plain_view(project: LiveProject, entry: RecommendationEntry) -> ExplanationView:
    """An AI explanation as a recommendation's page shows it."""
    assert entry.explanation is not None
    keys = {j: key for key, j in project.activity_ids().items()}
    nodes = project.nodes()
    names = {j: nodes[key].name for j, key in keys.items() if key in nodes}
    shown = llm_view(entry.explanation)
    return shown.model_copy(update={"text": plain_labels(shown.text, names)})


def plain_labels(text: str, names: Mapping[int, str]) -> str:
    """An AI text in a manager's words (spec section 11.7): the record it explains names actions
    by their labels and tasks by their numbers, and the model repeats them. Display only: the
    check of its faithfulness has read the text as written, and the log keeps it."""

    def task(match: re.Match[str]) -> str:
        return names.get(int(match.group(1)), "a task")

    for pattern, words in LABEL_WORDS:
        text = pattern.sub(words, text)
    return ACTIVITY_NUMBER.sub(task, text)


def _alternatives(
    candidates: Sequence[CandidateRecord], chosen: str, runner_up: str | None
) -> list[CandidateRecord]:
    """The other candidates of a recommendation stored before v2.0.2: the runner-up first,
    then those racing kept, then the rest."""
    others = [c for c in candidates if c.label != chosen]
    return sorted(others, key=lambda c: (c.label != runner_up, c.dropped, -c.capped, c.tardiness))


def llm_view(explanation: LlmExplanation) -> ExplanationView:
    if not explanation.valid or explanation.error is not None:
        badge: Literal["faithful", "unfaithful", "invalid"] = "invalid"
    elif explanation.fully_faithful:
        badge = "faithful"
    else:
        badge = "unfaithful"
    return ExplanationView(
        text=explanation.text,
        source="llm",
        model=explanation.model,
        badge=badge,
        facts_right=sum(f.correct for f in explanation.facts),
        facts=len(explanation.facts),
        hallucinated=explanation.hallucinated,
    )


def forecast_view(
    project: LiveProject, result: ForecastResult, threats: ThreatList | None = None
) -> ForecastView:
    """A forecast with its threat list if known; with no late future none is needed (11.4)."""
    calendar = project.calendar
    nodes = project.nodes()
    q10, q50, q90 = result.quantiles
    drivers = None
    if not result.late:
        drivers = []
    elif threats is not None:
        drivers = [
            DriverView(task=d.task, name=nodes[d.task].name, sensitivity=d.sensitivity)
            for d in threats.drivers
        ]
    return ForecastView(
        day=result.day,
        as_of=calendar.date_of(result.day),
        rollouts=result.rollouts,
        p_on_time=result.p_on_time,
        deadline=project.definition.deadline,
        p10=calendar.finish_date(q10),
        p50=calendar.finish_date(q50),
        p90=calendar.finish_date(q90),
        mean=result.mean,
        drivers=drivers,
        threat_rollouts=None if threats is None or not result.late else threats.rollouts,
        late=result.late,
        expected_cost=result.mean_cost,
        budget=project.require_model().budget,
        p_within_budget=result.p_within_budget,
    )
