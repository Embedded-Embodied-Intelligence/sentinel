"""What the API shows of a project, in the user's language (spec section 11): every day as a
calendar date, tasks and people by name, recommendations as plain-language actions with their
effect, issues as messages. The views are pydantic models, so the JSON API and the HTML pages
of WP9b render the same data.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sentinel.agent.decide import CandidateRecord
from sentinel.app.calendar import WorkCalendar
from sentinel.app.events import LiveState, LlmExplanation, RecommendationEntry, Source
from sentinel.app.live import Issue, LiveProject, validate_definition
from sentinel.app.messages import render
from sentinel.app.models import Language, ProjectDefinition
from sentinel.app.planning import ForecastResult, Impact, sentinel_params
from sentinel.dashboard.explain import template_explanation
from sentinel.policies.base import Decision, Descope, Overtime, Reseq, Shift, Subst
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
    """A task as the manager sees it: its definition, its progress and its plan."""

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
    """A candidate's effect: P(on time), expected finish date, expected cost and overrun."""

    p_on_time: float
    expected_finish: date | None
    tardiness: float
    expected_cost: float
    overrun: float
    rollouts: int


class ChangeView(View):
    task: str
    name: str
    old: date
    new: date


class AlternativeView(View):
    label: str
    title: str
    p_on_time: float
    tardiness: float
    expected_cost: float
    dropped: bool


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
    seq: int
    day: int
    date: date
    status: str
    status_text: str
    label: str
    kind: str
    title: str
    acts: bool
    level: int
    needs_approval: bool
    urgency: float | None
    can_wait: bool
    reason: str
    reason_text: str
    with_action: OutcomeView | None
    without: OutcomeView | None
    changes: list[ChangeView]
    alternatives: list[AlternativeView]
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
    baseline: BaselineView | None
    tasks: list[TaskView]
    people: list[PersonView]
    checkins: list[CheckinView]
    recommendations: list[RecommendationView]
    open_recommendation: int | None


class DriverView(View):
    task: str
    name: str
    share: float


class ForecastView(View):
    day: int
    as_of: date
    rollouts: int
    p_on_time: float | None
    deadline: date | None
    p10: date
    p50: date
    p90: date
    mean: float
    drivers: list[DriverView]


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
        baseline=None
        if baseline is None
        else BaselineView(
            makespan=baseline.makespan,
            finish=calendar.finish_date(baseline.makespan),
            method=baseline.method,
            status=baseline.status,
        ),
        tasks=task_views(project, observation, language),
        people=person_views(project, observation),
        checkins=[CheckinView(date=d, day=t) for d, t in project.checkins],
        recommendations=[recommendation_view(project, r, language) for r in state.recommendations],
        open_recommendation=None if state.open is None else state.open.seq,
    )


def task_views(
    project: LiveProject, observation: Observation | None, language: Language
) -> list[TaskView]:
    calendar = project.calendar
    definition = project.definition
    names = person_names(project)
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
        planned = tracked.planned if state == "not_started" else None
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
                late=planned is not None and planned < observation.day,
            )
        )
    return rows


def person_names(project: LiveProject) -> dict[str, str]:
    names = {p.key: p.name for p in project.definition.team}
    names.update({temp.key: temp.name for temp in project.temps})
    return names


def person_views(project: LiveProject, observation: Observation | None) -> list[PersonView]:
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
        for temp in project.temps:
            rows.append(
                PersonView(
                    key=temp.key,
                    name=temp.name,
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
    decision: Decision, kind: str, project: LiveProject, day: int, language: Language
) -> str:
    """The action of a decision in plain language (spec section 11.5)."""
    if not decision.operations:
        return render("action_noop", language)
    model = project.require_model()
    calendar = project.calendar
    keys = {j: key for key, j in project.activity_ids().items()}
    nodes = project.nodes()
    workers = project.worker_keys()
    names = person_names(project)
    parts = []
    plan_part = None
    for op in decision.operations:
        match op:
            case Subst():
                who = ", ".join(
                    names.get(workers[w], str(w)) for w in op.workers if w < len(workers)
                )
                parts.append(
                    render(
                        "action_subst",
                        language,
                        {"workers": who, "task": nodes[keys[op.activity]].name},
                    )
                )
            case Overtime():
                until = calendar.finish_date(day + op.days)
                parts.append(
                    render(
                        "action_overtime",
                        language,
                        {
                            "count": op.workers,
                            "role": model.role_names[op.role],
                            "days": op.days,
                            "until": until.isoformat(),
                        },
                    )
                )
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
    text = render("action_then", language).join(parts)
    return text[:1].upper() + text[1:]


def _outcome(impact: Impact | None, calendar: WorkCalendar) -> OutcomeView | None:
    if impact is None:
        return None
    finish = None
    if impact.mean_makespan is not None:
        finish = calendar.finish_date(int(impact.mean_makespan + 0.5))
    return OutcomeView(
        p_on_time=impact.p_on_time,
        expected_finish=finish,
        tardiness=impact.tardiness,
        expected_cost=impact.mean_cost,
        overrun=impact.overrun,
        rollouts=impact.rollouts,
    )


def recommendation_view(
    project: LiveProject, entry: RecommendationEntry, language: Language
) -> RecommendationView:
    recommendation = entry.recommendation
    record = recommendation.record
    calendar = project.calendar
    chosen = recommendation.chosen
    decision = chosen.decision if chosen is not None else record.decision
    kind = chosen.kind if chosen is not None else "noop"
    params = sentinel_params(project)
    nodes = project.nodes()
    alternatives = [
        AlternativeView(
            label=c.label,
            title=describe(c.decision, c.kind, project, recommendation.day, language),
            p_on_time=c.p_on_time,
            tardiness=c.tardiness,
            expected_cost=c.mean_cost,
            dropped=c.dropped,
        )
        for c in _alternatives(record.candidates, record.chosen, record.runner_up)
    ]
    reason = record.reason
    return RecommendationView(
        seq=entry.seq,
        day=recommendation.day,
        date=calendar.date_of(recommendation.day),
        status=entry.status,
        status_text=render(f"status_{entry.status}", language),
        label=record.chosen,
        kind=kind,
        title=describe(decision, kind, project, recommendation.day, language),
        acts=recommendation.acts,
        level=decision.level,
        needs_approval=recommendation.acts and params.needs_approval(decision),
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
        explanation=ExplanationView(
            text=template_explanation(record, language).summary, source="template"
        ),
        llm_explanation=None if entry.explanation is None else llm_view(entry.explanation),
        discarded=entry.discarded,
    )


def _alternatives(
    candidates: Sequence[CandidateRecord], chosen: str, runner_up: str | None
) -> list[CandidateRecord]:
    """The other candidates, the runner-up first, then those racing kept, then the rest."""
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


def forecast_view(project: LiveProject, result: ForecastResult) -> ForecastView:
    calendar = project.calendar
    nodes = project.nodes()
    q10, q50, q90 = result.quantiles
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
        drivers=[
            DriverView(task=d.task, name=nodes[d.task].name, share=d.share) for d in result.drivers
        ],
    )
