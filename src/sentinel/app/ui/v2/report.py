"""The v2 Raport (docs/design/v2-spec.md, section 8.3): what happened, written or dictated, read
by the AI into cards to confirm (unchecked by default, each editable and removable), questions
that block saving, the parts not recognised, "Postęp zgodny z planem", the effect of the draft on
the project as a dry-run forecast, and the save, after which Sentinel deliberates at the v2 gate.
Items travel in the form as the JSON of their reports, as in the first interface (WP14).

"Wypełnij formularz" (WP16) is the per-task form, whose fields are named as in the first
interface's check-in form and read by its reader (`forms.read_checkin`), so both validate alike;
what it says becomes cards, ticked, since the manager entered it. The scenarios of the
Laboratorium (section 8.8) use its rows for an absence, a longer task and a new task."""

import json
import secrets
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError

from sentinel.app.errors import AppError
from sentinel.app.message_reader import MessageDraft
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    NewTaskReport,
    TaskReport,
    WorkIncreaseReport,
)
from sentinel.app.planning import planned_reports
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import CheckinForm, Form, read_checkin
from sentinel.app.ui.project import message_values, shown_tasks
from sentinel.app.ui.v2.numbers import per_hundred
from sentinel.app.ui.v2.overview import Chip, tone_of
from sentinel.app.ui.v2.shell import GATE, PREFIX, header, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView, TaskView

KINDS: dict[str, type[BaseModel]] = {
    "task": TaskReport,
    "absence": AbsenceReport,
    "increase": WorkIncreaseReport,
    "new": NewTaskReport,
}
HINTS = ("absent", "done", "longer", "new")


@dataclass(frozen=True)
class Edit:
    """A field of a card's ✎: the report's field, its label, the input's type and value."""

    name: str
    label: str
    kind: str
    value: str


@dataclass(frozen=True)
class Card:
    """An item to confirm: its kind, the JSON of its report, its words, its fields to edit."""

    kind: str
    value: str
    text: str
    icon: str
    edits: list[Edit] = field(default_factory=list)
    note: str | None = None


@dataclass(frozen=True)
class Choice:
    value: str
    text: str


@dataclass(frozen=True)
class Question:
    """A question that blocks saving until it is answered or skipped (section 8.3)."""

    text: str
    hint: str
    choices: list[Choice]


def default_date(view: ProjectView, today: date) -> date:
    """The report's date: today, or the first working day after the latest report if that is
    later (a report comes after the previous one, spec section 11.1)."""
    if not view.checkins:
        return max(today, view.definition.start)
    last = view.checkins[-1].date
    after = last + timedelta(days=1)
    while after.weekday() >= 5:
        after += timedelta(days=1)
    return max(today, after)


def card_of(
    t: TextsV2, item: BaseModel, names: dict[str, str], people: dict[str, str], note: str | None
) -> Card:
    """The card of a report, with its words and the fields its ✎ edits."""
    value = item.model_dump_json()
    if isinstance(item, TaskReport):
        name = names.get(item.task, item.task)
        if item.status == "done" and item.finish is not None:
            edits = [Edit("finish", t("v2.edit.finish"), "date", item.finish.isoformat())]
            return Card(
                "task",
                value,
                t("v2.card.done", task=name, date=t.date(item.finish)),
                "check-circle",
                edits,
                note,
            )
        percent = round(item.percent or 0)
        edits = [Edit("percent", t("v2.edit.percent"), "number", str(percent))]
        if item.start is not None:
            text = t("v2.card.started", task=name, date=t.date(item.start), percent=percent)
        else:
            text = t("v2.card.progress", task=name, percent=percent)
        return Card("task", value, text, "play", edits, note)
    if isinstance(item, AbsenceReport):
        person = people.get(item.person, item.person)
        edits = [Edit("first_day", t("v2.edit.first"), "date", item.first_day.isoformat())]
        if item.return_date is not None:
            edits.append(
                Edit("return_date", t("v2.edit.back"), "date", item.return_date.isoformat())
            )
            text = t(
                "v2.card.absence",
                name=person,
                first=t.date(item.first_day),
                back=t.date(item.return_date),
            )
        else:
            text = t("v2.card.absence_open", name=person, first=t.date(item.first_day))
        return Card("absence", value, text, "person-off", edits, note)
    if isinstance(item, WorkIncreaseReport):
        task = names.get(item.task, item.task)
        if item.extra_days is not None:
            days = t.decimal(item.extra_days)
            edits = [Edit("extra_days", t("v2.edit.days"), "number", days.replace(",", "."))]
            return Card(
                "increase", value, t("v2.card.more", task=task, n=days), "clock", edits, note
            )
        factor = t.decimal(item.factor or 1.0)
        return Card("increase", value, t("v2.card.factor", task=task, f=factor), "clock", [], note)
    assert isinstance(item, NewTaskReport)
    edits = [Edit("duration", t("v2.edit.duration"), "number", str(item.duration))]
    return Card(
        "new", value, t("v2.card.new", name=item.name, n=item.duration), "plus", edits, note
    )


def message_cards(
    ui: Ui, request: Request, project_id: str, found: MessageDraft, clauses: tuple[str, ...]
) -> dict[str, Any]:
    """The cards, questions and unrecognised parts of a message read by the AI (WP14)."""
    t = texts(request)
    values = message_values(ui, request, project_id, found)
    names, people = values["names"], values["people"]
    unchecked = t("checkin.message_unchecked")
    cards: list[Card] = []
    for i, task in enumerate(found.tasks):
        cards.append(
            card_of(t, task, names, people, unchecked if i in found.unchecked_tasks else None)
        )
    for i, absence in enumerate(found.absences):
        note = (
            t("checkin.message_doubtful")
            if i in found.doubtful
            else (unchecked if i in found.unchecked_absences else None)
        )
        cards.append(card_of(t, absence, names, people, note))
    cards += [card_of(t, item, names, people, None) for item in found.increases]
    cards += [card_of(t, item, names, people, None) for item in found.new_tasks]

    def clause(n: int) -> str:
        return f"„{clauses[n - 1]}”" if 0 < n <= len(clauses) else t("checkin.message_clause", n=n)

    kinds = {TaskReport: "task", AbsenceReport: "absence", WorkIncreaseReport: "increase"}

    def choice(item: BaseModel) -> Choice:
        text = card_of(t, item, names, people, None).text
        return Choice(f"{kinds[type(item)]}:{item.model_dump_json()}", text)

    questions: list[Question] = []
    for q in found.questions:
        options: list[BaseModel] = []
        hint = values["date_problem"](q)
        if q.kind == "unknown_person":
            text = t("checkin.message_unknown_person", clause=clause(q.clause))
            dates = [(a.first_day, a.return_date) for a in q.absences]
            if not dates and q.first_day is not None:
                dates = [(q.first_day, q.return_date)]
            for key in people:
                options += [AbsenceReport(person=key, first_day=a, return_date=b) for a, b in dates]
            hint = hint if q.absences else ""
        elif q.kind == "ambiguous_task":
            text = t("checkin.message_ambiguous_task", clause=clause(q.clause))
            options = [*q.tasks, *q.increases]
            if not options:
                options = [
                    WorkIncreaseReport(task=key, extra_days=q.extra_days, factor=q.factor)
                    for key in q.candidates
                ]
            hint = ""
        else:
            text = t("checkin.message_date_question", clause=clause(q.clause))
            options = [*q.tasks, *q.absences]
        questions.append(Question(text, hint, [choice(item) for item in options]))
    unparsed = [clause(n) for n in found.unparsed]
    return {"cards": cards, "questions": questions, "unparsed": unparsed}


@dataclass(frozen=True)
class Draft:
    """A report as the form holds it: the check-in of the ticked cards and answered questions
    (None if it is not valid), the questions still open, and whether anything was ticked."""

    checkin: CheckIn | None
    open_questions: int
    ticked: int
    planned: bool
    error: str | None = None


def read_draft(form: Form, view: ProjectView, t: TextsV2) -> Draft:
    try:
        day = date.fromisoformat(form.get("date"))
    except ValueError:
        return Draft(None, 0, 0, False, t("v2.failed"))
    items: dict[str, list[BaseModel]] = {kind: [] for kind in KINDS}
    ticked = 0
    try:
        for kind, model in KINDS.items():
            for value in form.getlist(f"c_{kind}"):
                if value:
                    items[kind].append(model.model_validate_json(value))
                    ticked += 1
        open_questions = 0
        for i in range(int(form.get("qn") or 0)):
            answer = form.get(f"q-{i}")
            if not answer:
                open_questions += 1
            elif answer != "skip":
                kind, _, value = answer.partition(":")
                if kind in KINDS:
                    items[kind].append(KINDS[kind].model_validate_json(value))
                    ticked += 1
    except (ValidationError, ValueError, json.JSONDecodeError):
        return Draft(None, 0, 0, False, t("v2.failed"))
    tasks: dict[str, TaskReport] = {}
    for item in items["task"]:
        assert isinstance(item, TaskReport)
        tasks[item.task] = item  # the last one of a task wins, as in the first form
    try:
        checkin = CheckIn(
            date=day,
            tasks=tuple(tasks.values()),
            absences=tuple(i for i in items["absence"] if isinstance(i, AbsenceReport)),
            increases=tuple(i for i in items["increase"] if isinstance(i, WorkIncreaseReport)),
            new_tasks=tuple(i for i in items["new"] if isinstance(i, NewTaskReport)),
        )
    except ValidationError:
        return Draft(None, open_questions, ticked, False, t("v2.failed"))
    return Draft(checkin, open_questions, ticked, form.flag("planned_used"))


def stalled_tasks(view: ProjectView, checkin: CheckIn) -> int:
    """Running tasks the draft says nothing about (section 8.3 "bez wieści")."""
    named = {report.task for report in checkin.tasks}
    return sum(
        1
        for task in view.tasks
        if task.state in ("in_progress", "paused") and task.key not in named
    )


@dataclass(frozen=True)
class Choices:
    """What the selects of the form and the scenarios offer: the tasks the form asks about, the
    people, the roles, the tasks that can still take longer and those a new task can follow,
    and the fields to correct with their messages."""

    tasks: list[TaskView]
    people: list[tuple[str, str]]
    roles: list[str]
    open_tasks: list[TaskView]
    all_tasks: list[TaskView]
    errors: dict[str, str] = field(default_factory=dict)


def choices(view: ProjectView, errors: dict[str, str] | None = None) -> Choices:
    first, _ = shown_tasks(view)
    tasks = [task for task in view.tasks if task.state != "removed"]
    return Choices(
        tasks=first,
        people=[(p.key, p.name) for p in view.definition.team],
        roles=sorted({p.role for p in view.definition.team}),
        open_tasks=[task for task in tasks if task.state != "done"],
        all_tasks=tasks,
        errors=errors or {},
    )


def read_items(form: Form, view: ProjectView) -> CheckinForm:
    """The form's fields as a check-in: only changes are reported, as in the first form; a share
    is compared as the form shows it, in whole per cent, so an untouched field is no change."""
    current = {
        task.key: (
            task.state if task.state != "paused" else "in_progress",
            None if task.percent is None else float(round(task.percent)),
        )
        for task in view.tasks
    }
    return read_checkin(form, current)


def items_of(checkin: CheckIn) -> list[BaseModel]:
    return [*checkin.tasks, *checkin.absences, *checkin.increases, *checkin.new_tasks]


def cards_of(t: TextsV2, view: ProjectView, checkin: CheckIn) -> list[Card]:
    """The cards of a check-in's items, with the names of the tasks and the people."""
    names = {task.key: task.name for task in view.tasks}
    people = {p.key: p.name for p in view.definition.team}
    return [card_of(t, item, names, people, None) for item in items_of(checkin)]


def errors_of(t: TextsV2, read: CheckinForm) -> dict[str, str]:
    return {error.name: t(error.key, **error.values) for error in read.errors}


def day_of(form: Form, view: ProjectView) -> date:
    """The report's date the form travels with (its default if the field is not a date)."""
    try:
        return date.fromisoformat(form.get("date"))
    except ValueError:
        return default_date(view, date.today())


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def live(request: Request, project_id: str) -> ProjectView:
        return services.live(ui.session(request), project_id, ui.language(request))

    @routes.get(PREFIX + "/projects/{project_id}/report")
    def report_page(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        if not view.has_plan:
            return ui.redirect(request, f"{PREFIX}/new/{project_id}")
        t = texts(request)
        day = default_date(view, date.today())
        return page(
            ui,
            request,
            "report.html",
            title=t("v2.report.title"),
            nav="projects",
            tab="report",
            project=header(ui, request, view),
            view=view,
            day=day,
            last=view.checkins[-1].date if view.checkins else None,
            hints=[(key, t(f"v2.hint.{key}"), t(f"v2.hint.{key}.text")) for key in HINTS],
            choices=choices(view),
            kept=None,
            oob=False,
            nothing=False,
            lab_cards=[],
        )

    @routes.post(PREFIX + "/projects/{project_id}/report/read")
    async def read(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        try:
            day = date.fromisoformat(form.get("date"))
        except ValueError:
            day = date.today()
        job = services.read_message(
            ui.session(request), project_id, form.get("message"), day, ui.language(request)
        )
        return page(
            ui,
            request,
            "_cards.html",
            project_id=project_id,
            job=job.id,
            cards=[],
            questions=[],
            unparsed=[],
            failed=None,
            source="message",
        )

    @routes.get(PREFIX + "/projects/{project_id}/report/read")
    def read_poll(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        job_id = request.query_params.get("job", "")
        job = services.job(session, job_id, language)
        values: dict[str, Any] = {"cards": [], "questions": [], "unparsed": [], "failed": None}
        if job.status == "done":
            found = MessageDraft.model_validate(job.result or {})
            values = message_cards(ui, request, project_id, found, services.message_clauses(job_id))
            values["failed"] = None
            if not (values["cards"] or values["questions"] or values["unparsed"]):
                values["failed"] = texts(request)("checkin.message_nothing")
        elif job.status == "failed":
            values["failed"] = (
                job.error.message if job.error is not None else texts(request)("v2.failed")
            )
        waiting = job.status in ("queued", "running")
        return page(
            ui,
            request,
            "_cards.html",
            project_id=project_id,
            job=job_id if waiting else None,
            source="message",
            **values,
        )

    @routes.post(PREFIX + "/projects/{project_id}/report/planned")
    async def planned(request: Request, project_id: str) -> Response:
        """ "Postęp zgodny z planem": the progress the plan expected by the report's date."""
        form = await Form.read(request)
        t = texts(request)
        try:
            day = date.fromisoformat(form.get("date"))
        except ValueError:
            day = date.today()
        state = services.state(ui.session(request), project_id)
        project = state.project
        found = planned_reports(project, project.calendar.checkin_day(day)) or ()
        names = {key: node.name for key, node in project.nodes().items()}
        cards = []
        for report in found:
            name = names.get(report.task, report.task)
            card = card_of(t, report, names, {}, None)
            if report.status == "done" and report.finish is not None:
                text = t("v2.card.planned_done", task=name, date=t.date(report.finish))
            else:
                text = t("v2.card.planned", task=name, percent=round(report.percent or 0))
            cards.append(Card(card.kind, card.value, text, card.icon, card.edits))
        return page(
            ui,
            request,
            "_cards.html",
            project_id=project_id,
            job=None,
            cards=cards,
            questions=[],
            unparsed=[],
            failed=None if cards else t("v2.week.empty"),
            source="planned",
        )

    @routes.post(PREFIX + "/projects/{project_id}/report/impact")
    async def impact(request: Request, project_id: str) -> Response:
        """ "Wpływ na projekt": the draft's dry-run forecast against the forecast now."""
        form = await Form.read(request)
        t = texts(request)
        view = live(request, project_id)
        draft = read_draft(form, view, t)
        chips: list[Chip] = []
        error = draft.error
        stalled = 0
        if draft.checkin is not None and draft.ticked:
            try:
                before, after = services.dry_run(ui.session(request), project_id, draft.checkin)
            except AppError as exc:
                error = " ".join(t.issues(exc))
            else:
                if before.p_on_time is not None and after.p_on_time is not None:
                    a, b = per_hundred(before.p_on_time), per_hundred(after.p_on_time)
                    chips.append(Chip(t("v2.effect.chance", before=a, after=b), tone_of(b - a)))
                tone = tone_of((after.p50 - before.p50).days, better_up=False)
                chips.append(
                    Chip(
                        t("v2.effect.end", before=t.date(before.p50), after=t.date(after.p50)), tone
                    )
                )
            stalled = stalled_tasks(view, draft.checkin)
        can_save = (
            draft.checkin is not None
            and error is None
            and draft.open_questions == 0
            and (draft.ticked > 0 or draft.planned)
        )
        last = view.checkins[-1].date if view.checkins else view.definition.start
        return page(
            ui,
            request,
            "_impact.html",
            chips=chips,
            error=error,
            blocked=draft.open_questions > 0,
            ticked=draft.ticked,
            can_save=can_save,
            stalled=stalled,
            last=last,
        )

    @routes.post(PREFIX + "/projects/{project_id}/report/form")
    async def add_from_form(request: Request, project_id: str) -> Response:
        """ "Wypełnij formularz" → "Dodaj do raportu": the form's items as ticked cards and the
        form emptied again, or kept with what needs a correction."""
        form = await Form.read(request)
        t = texts(request)
        view = live(request, project_id)
        read = read_items(form, view)
        values: dict[str, Any] = {"view": view, "day": day_of(form, view), "oob": True}
        if read.checkin is None:
            return page(
                ui,
                request,
                "_form_result.html",
                cards=[],
                choices=choices(view, errors_of(t, read)),
                kept=form,
                nothing=False,
                **values,
            )
        cards = cards_of(t, view, read.checkin)
        return page(
            ui,
            request,
            "_form_result.html",
            cards=cards,
            choices=choices(view),
            kept=None,
            nothing=not cards,
            project_id=project_id,
            job=None,
            questions=[],
            unparsed=[],
            failed=None,
            source=f"form-{secrets.token_hex(3)}",
            checked=True,
            **values,
        )

    @routes.post(PREFIX + "/projects/{project_id}/report")
    async def save(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        t = texts(request)
        view = live(request, project_id)
        draft = read_draft(form, view, t)
        if draft.checkin is None or draft.open_questions or not (draft.ticked or draft.planned):
            raise AppError("field_invalid", field="report", detail="")
        services.checkin(
            ui.session(request), project_id, draft.checkin, ui.language(request), autonomy=GATE
        )
        return ui.redirect(request, f"{PREFIX}/projects/{project_id}", done="report")

    return routes
