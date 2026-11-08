"""The v2 Laboratorium (docs/design/v2-spec.md, section 8.8). "Co jeśli?": on a chosen project, a
person absent, a task taking longer or a new task, shown as "Wpływ na projekt" (the Raport's dry
run, dated at the latest report so that only the scenario moves the forecast), nothing saved;
"Dodaj do raportu" opens the Raport with these items as ticked cards. "Symulator": the first
interface's simulator restyled, "Mało zakłóceń" or "Dużo zakłóceń", Sentinel against nobody
reacting on the same events, advanced by a day, five days or to the end with a day counter, and
one sentence for the board at the end."""

import contextlib
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.calendar import WorkCalendar
from sentinel.app.errors import AppError
from sentinel.app.simulator import SimulatorSpec, SimulatorView
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form
from sentinel.app.ui.sim import END, EXAMPLES, compare_rows, latest_chance, timeline, verdict
from sentinel.app.ui.v2.numbers import per_hundred, state_of
from sentinel.app.ui.v2.overview import Chip, signed, tone_of
from sentinel.app.ui.v2.report import choices, errors_of, items_of, read_items
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ForecastView, ProjectView

TABS = ("whatif", "sim")
LEVELS = {"low": "calm", "high": "turbulent"}  # "Mało zakłóceń", "Dużo zakłóceń"
STEPS = ("1", "5", "end")
KINDS = {"absence": "absences", "increase": "increases", "new": "new_tasks"}


def scenario_date(view: ProjectView) -> date:
    """The date of a scenario's dry run: the latest report's, so that no day passes and only
    the scenario moves the forecast (the project's start before the first report)."""
    return view.checkins[-1].date if view.checkins else view.definition.start


def impact_chips(
    t: TextsV2, before: ForecastView, after: ForecastView, person_days: bool
) -> list[Chip]:
    """The chance in 100, the most likely end and the expected budget, before and after."""
    chips = []
    if before.p_on_time is not None and after.p_on_time is not None:
        a, b = per_hundred(before.p_on_time), per_hundred(after.p_on_time)
        chips.append(Chip(t("v2.effect.chance", before=a, after=b), tone_of(b - a)))
    moved = (after.p50 - before.p50).days
    end = t("v2.effect.end", before=t.date(before.p50), after=t.date(after.p50))
    chips.append(Chip(end, tone_of(moved, better_up=False)))
    if before.expected_cost is not None and after.expected_cost is not None:
        cost = after.expected_cost - before.expected_cost
        key = "v2.effect.budget" if person_days else "v2.effect.budget_units"
        tone = tone_of(cost, better_up=False, eps=0.5)
        chips.append(Chip(t(key, change=signed(t, cost)), tone))
    return chips


@dataclass(frozen=True)
class SimEntry:
    """A simulator project of the session: its link, name, day and whether it ended."""

    href: str
    name: str
    day: int
    total: int
    finished: bool
    level: str


def total_days(view: SimulatorView) -> int:
    """The length a run reads as "of about": the original plan's days, or the days run if more."""
    calendar = WorkCalendar(view.spec.start)
    return max(calendar.last(view.baseline_finish) + 1, view.days, 1)


def level_of(spec: SimulatorSpec) -> str:
    return "high" if spec.disruptions == "turbulent" else "low"


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def planned_projects(request: Request) -> list[tuple[str, str]]:
        session, language = ui.session(request), ui.language(request)
        found = []
        for summary in services.projects(session):
            if summary.kind != "live":
                continue
            view = services.live(session, summary.id, language)
            if view.has_plan and not view.finished:
                found.append((summary.id, view.name))
        return found

    def simulations(request: Request) -> list[SimEntry]:
        session, language = ui.session(request), ui.language(request)
        found = []
        for summary in services.projects(session):
            if summary.kind != "simulator":
                continue
            with contextlib.suppress(AppError):
                view = services.simulator(session, summary.id, language)
                found.append(
                    SimEntry(
                        f"{PREFIX}/lab/sim/{summary.id}",
                        view.name,
                        view.days,
                        total_days(view),
                        view.finished,
                        level_of(view.spec),
                    )
                )
        return found

    @routes.get(PREFIX + "/lab")
    def lab(request: Request) -> Response:
        t = texts(request)
        tab = request.query_params.get("tab", "whatif")
        tab = tab if tab in TABS else "whatif"
        values: dict[str, Any] = {"tab_shown": tab}
        if tab == "whatif":
            projects = planned_projects(request)
            picked = request.query_params.get("project")
            chosen = next((pid for pid, _ in projects if pid == picked), None)
            if chosen is None and projects:
                chosen = projects[0][0]
            values["projects"] = projects
            values["chosen"] = chosen
            if chosen is not None:
                view = services.live(ui.session(request), chosen, ui.language(request))
                values["view"] = view
                values["choices"] = choices(view)
                values["day"] = scenario_date(view)
        else:
            available = [e for e in EXAMPLES if e.instance in services.instances(e.set_name)]
            values["examples"] = available
            values["runs"] = simulations(request)
        return page(
            ui,
            request,
            "lab.html",
            title=t("v2.lab.title"),
            nav="lab",
            kept=None,
            **values,
        )

    @routes.post(PREFIX + "/lab/whatif/{project_id}")
    async def whatif(request: Request, project_id: str) -> Response:
        """ "Wpływ na projekt" of a scenario: the dry run of its items, nothing saved."""
        form = await Form.read(request)
        t = texts(request)
        session, language = ui.session(request), ui.language(request)
        view = services.live(session, project_id, language)
        read = read_items(form, view)
        values: dict[str, Any] = {"project_id": project_id, "chips": [], "error": None}
        values["errors"] = errors_of(t, read)
        values["link"] = None
        if read.checkin is None:
            values["error"] = t("v2.form.fix")
            return page(ui, request, "_lab_impact.html", **values)
        items = items_of(read.checkin)
        if not items:
            values["error"] = t("v2.lab.nothing")
            return page(ui, request, "_lab_impact.html", **values)
        try:
            before, after = services.dry_run(session, project_id, read.checkin)
        except AppError as exc:
            values["error"] = " ".join(t.issues(exc))
            return page(ui, request, "_lab_impact.html", **values)
        values["chips"] = impact_chips(t, before, after, view.person_days)
        query = []
        for item in items:
            kind = {"AbsenceReport": "absence", "WorkIncreaseReport": "increase"}.get(
                type(item).__name__, "new"
            )
            query.append((f"c_{kind}", item.model_dump_json()))
        values["link"] = f"{PREFIX}/projects/{project_id}/report?{urlencode(query)}"
        return page(ui, request, "_lab_impact.html", **values)

    # ---- the simulator

    def wait(request: Request, job_id: str, target: str, label: str, total: str = "") -> Response:
        """The progress of a job of the simulator, which polls until the job ends."""
        return page(
            ui,
            request,
            "_lab_wait.html",
            job=services.job(ui.session(request), job_id, ui.language(request)),
            target=target,
            label=label,
            total=total,
        )

    @routes.post(PREFIX + "/lab/sim")
    async def create(request: Request) -> Response:
        form = await Form.read(request)
        t = texts(request)
        example = next((e for e in EXAMPLES if e.key == form.get("example")), EXAMPLES[0])
        level = form.get("level", "low")
        if level not in LEVELS:
            raise AppError("invalid_request")
        spec = SimulatorSpec(
            name=f"{t(f'sim.name.{example.size}')} · {t(f'v2.lab.level.{level}')}",
            set_name=example.set_name,  # type: ignore[arg-type]
            instance=example.instance,
            scenario=example.scenario,
            start=date.today(),
            disruptions=LEVELS[level],  # type: ignore[arg-type]
            policy="sentinel",
        )
        job = services.create_simulator(ui.session(request), spec, ui.language(request))
        target = f"{PREFIX}/lab/sim/{job.project}" if job.project else f"{PREFIX}/lab?tab=sim"
        return wait(request, job.id, target, "v2.lab.preparing")

    @routes.get(PREFIX + "/lab/wait")
    def waiting(request: Request) -> Response:
        """A job of the simulator, polled until it ends; then the page it leads to."""
        job_id = request.query_params.get("job", "")
        target = request.query_params.get("next", f"{PREFIX}/lab?tab=sim")
        if not target.startswith(PREFIX + "/lab"):
            target = f"{PREFIX}/lab?tab=sim"
        job = services.job(ui.session(request), job_id, ui.language(request))
        if job.status == "done":
            return ui.redirect(request, target)
        label = request.query_params.get("label", "v2.lab.preparing")
        label = label if label in ("v2.lab.preparing", "v2.lab.running") else "v2.lab.preparing"
        return wait(request, job_id, target, label, total=request.query_params.get("total", ""))

    @routes.get(PREFIX + "/lab/sim/{project_id}")
    def simulation(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        t = texts(request)
        row = services.store.project(session, project_id)
        if row is None or row.kind != "simulator":
            raise AppError("project_not_found", "not_found")
        target = f"{PREFIX}/lab/sim/{project_id}"
        values: dict[str, Any] = {"name": row.name, "sim_id": project_id, "waiting": None}
        moving = services.store.project_jobs(session, project_id)
        job = None
        if moving:
            job = services.job(session, moving[0].id, language)
        elif not services.simulation_ready(session, project_id):
            with contextlib.suppress(AppError):
                job = services.load_simulation(session, project_id, language)
        if job is not None and job.status in ("queued", "running"):
            values["waiting"] = job
            return page(
                ui, request, "lab_sim.html", title=row.name, nav="lab", target=target, **values
            )
        view = services.simulator(session, project_id, language)

        def read(simulation: Any) -> tuple[list[Any], tuple[float, int] | None]:
            return timeline(simulation.main, t), latest_chance(simulation.main)

        entries, chance = services.with_simulation(session, project_id, read)
        sides = [view.main] + ([view.compare] if view.compare is not None else [])
        calendar = WorkCalendar(view.spec.start)
        n = None if chance is None else per_hundred(chance[0])
        values.update(
            sim=view,
            sides=sides,
            total=total_days(view),
            level=level_of(view.spec),
            chance=n,
            chance_state=None if n is None else state_of(n),
            chance_date=None if chance is None else calendar.date_of(chance[1]),
            entries=entries[:8],  # the latest, newest first
            verdict=verdict(sides, t) if view.finished else "",
            rows=compare_rows(sides, t) if view.finished else [],
            steps=STEPS,
        )
        return page(
            ui, request, "lab_sim.html", title=view.name, nav="lab", target=target, **values
        )

    @routes.post(PREFIX + "/lab/sim/{project_id}/advance")
    async def advance(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        choice = form.get("days", "1")
        if choice not in STEPS:
            raise AppError("invalid_request")
        session, language = ui.session(request), ui.language(request)
        days = (
            int(choice)
            if choice != "end"
            else (ui.config.limits.simulator_days if ui.config.demo else None) or END
        )
        job = services.advance(session, project_id, days, language)
        view = services.simulator(session, project_id, language)
        target = f"{PREFIX}/lab/sim/{project_id}"
        return wait(request, job.id, target, "v2.lab.running", total=str(total_days(view)))

    return routes
