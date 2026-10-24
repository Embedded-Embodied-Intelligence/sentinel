"""Cockpit pages of the application's projects (WP8 cockpit, ADR-0021; spec section 11).

A finished simulator project gets the WP8 cockpit itself: its world and both runs are handed to
the cockpit's assembly (`kpis`, `gantt_rows`, `day_events`, `decision_log`, `forecasts`) and
page, so the page is the one `sentinel dashboard` writes for a study world. A live project gets
the cockpit's charts and style on its own data: the baseline plan over the work reported so far
(segments split by the reported absences), the check-in events, P(on time) and the makespan
band of every recommendation (NOOP's rollouts repeated on the recommendation's own worlds, as in
the cockpit), the recommendations with their decisions and explanations, and the provenance.
Tooltips name tasks and people and show calendar dates.
"""

import platform
from collections.abc import Sequence
from dataclasses import replace
from html import escape
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np

from sentinel.agent.candidates import noop
from sentinel.agent.evaluate import Evaluator
from sentinel.agent.params import SentinelParams
from sentinel.app.calendar import WorkCalendar
from sentinel.app.errors import AppError
from sentinel.app.events import LiveState, RecommendationEntry, replay
from sentinel.app.live import LiveProject
from sentinel.app.messages import render
from sentinel.app.models import Language
from sentinel.app.planning import sentinel_params
from sentinel.app.simulator import PolicyRun as SimRun
from sentinel.app.simulator import Simulation
from sentinel.app.store import EventRow
from sentinel.app.views import describe, llm_view, person_names
from sentinel.dashboard import svg
from sentinel.dashboard.assemble import (
    DayEvents,
    Row,
    Segment,
    day_events,
    decision_log,
    gantt_rows,
    kpis,
)
from sentinel.dashboard.cockpit import Cockpit, Options, Provenance, Side, explained
from sentinel.dashboard.explain import template_explanation
from sentinel.dashboard.labels import COLORS, DEADLINE, INK_2, Text
from sentinel.dashboard.page import CSS, SCRIPT
from sentinel.dashboard.page import render as render_page
from sentinel.dashboard.world import Forecast, PolicyRun, World, forecasts, load_catalogue
from sentinel.experiments.policy_config import PolicyStudyConfig
from sentinel.experiments.policy_runs import SentinelVariant
from sentinel.experiments.runs import git_state, load_toml
from sentinel.policies.base import DecisionStats
from sentinel.simulation.engine import Substitution

WORLD_CONFIG = Path("configs/wp5_rq4_main.toml")  # world settings of the studies
LIVE_COLOR = COLORS[6]  # Sentinel's slot of the WP4/WP5 figures
GIT_EXCLUDE = ("results", "paper/generated", "docs/dashboard")


# --------------------------------------------------------------------------- simulator


def simulator_page(simulation: Simulation, language: Language) -> str:
    """The WP8 cockpit of a finished simulator project (both runs to their end)."""
    world = _world(simulation)
    first = _side(world, simulation.main)
    if simulation.compare is None:
        raise AppError("simulation_running", "conflict")
    second = _side(world, simulation.compare)
    spec = simulation.world.spec
    options = Options(
        set_name=spec.set_name,
        instance=spec.instance,
        replication=spec.scenario,
        lambda_a=world.lambda_a,
        delta_d=spec.delta_d,
        policy=first.run.name,
        compare=second.run.name,
        language=language,
    )
    command = (
        f"sentinel ui, simulator project: {spec.set_name}/{spec.instance}, scenario "
        f"{spec.scenario}, policy {spec.policy}, autonomy {spec.autonomy}, presets "
        f"{spec.estimation}/{spec.disruptions}"
    )
    cockpit = Cockpit(
        options=options,
        world=world,
        first=first,
        second=second,
        forecasts=tuple(forecasts(world, first.run)),
        log=tuple(decision_log(world, first.run)) if first.run.is_sentinel else (),
        explanations=(),
        explain_source="template",
        provenance=_provenance(command),
        catalogue=load_catalogue(),
    )
    return render_page(explained(cockpit, None, language))


def _world(simulation: Simulation) -> World:
    sim = simulation.world
    spec = sim.spec
    if sim.reference is None:
        raise AppError("psplib_missing", "unavailable")
    config = PolicyStudyConfig.model_validate(load_toml(WORLD_CONFIG))
    config = config.model_copy(update={"pert": spec.pert})
    disruptions = spec.disruption_params
    return World(
        set_name=spec.set_name,
        stem=spec.instance,
        replication=spec.scenario,
        seed=spec.seed,
        lambda_a=disruptions.lambda_a,
        disruptions=disruptions,
        instance=sim.instance,
        plan=sim.plan,
        c_star=sim.c_star,
        reference=sim.reference,
        delta_d=spec.delta_d,
        deadline=sim.deadline,
        budget=sim.budget,
        config=config,
    )


def _side(world: World, run: SimRun) -> Side:
    sentinel = run.sentinel
    result = run.result()
    if sentinel is not None:
        name = "sentinel_full"
        variant: SentinelVariant | None = SentinelVariant(
            params=sentinel.params, delta_d=run.world.spec.delta_d
        )
        stats: DecisionStats = sentinel.stats
        records = tuple(sentinel.records)
        observations = run.observations
        params = sentinel.params
    else:
        name, variant, stats, records = run.name, None, DecisionStats(), ()
        observations = {o.day: o for o in result.observations}
        params = SentinelParams()
    policy_run = PolicyRun(
        name=name,
        variant=variant,
        result=result,
        stats=stats,
        records=records,
        observations=observations,
        params=params,
        sim_deadline=world.deadline,
    )
    return Side(
        policy_run,
        kpis(world, policy_run),
        tuple(gantt_rows(world, result)),
        tuple(day_events(result)),
    )


def _provenance(command: str) -> Provenance:
    git = git_state(GIT_EXCLUDE)
    software = [("Python", platform.python_version())]
    for package in ("sentinel", "numpy", "ortools", "pydantic", "fastapi"):
        try:
            software.append((package, version(package)))
        except PackageNotFoundError:  # pragma: no cover - installed with the project
            software.append((package, "?"))
    return Provenance(git["commit"], git["dirty"], tuple(software), command)


# --------------------------------------------------------------------------- live projects


class LiveText(Text):
    """The cockpit's words with a live project's names and dates in the tooltips."""

    def __init__(
        self,
        language: Language,
        calendar: WorkCalendar,
        tasks: dict[int, str],
        roles: Sequence[str],
        people: Sequence[str],
    ) -> None:
        super().__init__(language)
        self.calendar = calendar
        self.tasks = tasks
        self.roles = tuple(roles)
        self.people = tuple(people)

    def _date(self, day: int) -> str:
        return self.calendar.date_of(day).isoformat()

    def _task(self, j: int) -> str:
        return self.tasks.get(j, str(j))

    def role(self, k: int) -> str:
        return self.roles[k]

    def activity_tip(self, row: Row) -> str:
        return f"{self._task(row.activity)}: {row.duration} d, {self.crew(row.demands)}"

    def planned_tip(self, row: Row) -> str:
        assert row.planned is not None
        first, last = row.planned, row.planned + row.duration - 1
        return f"{self._task(row.activity)}: plan {self._date(first)} – {self._date(last)}"

    def segment_tip(self, row: Row, segment: Segment) -> str:
        first, last = segment.start, max(segment.start, segment.end - 1)
        crew = f"{segment.present}/{row.crew}"
        return f"{self._task(row.activity)}: {self._date(first)} – {self._date(last)}, {crew}"

    def paused_tip(self, first: int, end: int) -> str:
        return f"{self['legend_paused']}: {self._date(first)} – {self._date(max(first, end - 1))}"

    def substitution_tip(self, substitution: Substitution) -> str:
        who = ", ".join(
            self.people[w] if w < len(self.people) else str(w) for w in substitution.workers
        )
        return f"{self._date(substitution.day)}: {who} → {self._task(substitution.activity)}"

    def shock_tip(self, row: Row, day: int, factor: float) -> str:
        return f"{self._date(day)}: {self._task(row.activity)} ×{self.num(factor, 2)}"

    def inserted_tip(self, row: Row) -> str:
        assert row.inserted_day is not None
        return f"{self._date(row.inserted_day)}: + {self._task(row.activity)}"

    def descoped_tip(self, row: Row) -> str:
        assert row.descoped_day is not None
        return f"{self._date(row.descoped_day)}: - {self._task(row.activity)}"

    def absences_tip(self, day: DayEvents) -> str:
        names = [self.people[w] for w, _ in day.crew_absences]
        names += [self.people[w] for w in day.idle_absences]
        return f"{self._date(day.day)}: {', '.join(names)}"

    def work_tip(self, day: DayEvents) -> str:
        items = [f"{self._task(j)} ×{self.num(f, 2)}" for j, f in day.work_increases]
        return f"{self._date(day.day)}: {'; '.join(items)}"

    def new_tip(self, day: DayEvents) -> str:
        items = [f"+ {self._task(j)} ({p} d)" for j, p in day.new_activities]
        return f"{self._date(day.day)}: {'; '.join(items)}"

    def forecast_tip(self, forecast: Forecast) -> str:
        return (
            f"{self._date(forecast.day)}: P = {self.num(forecast.p_on_time, 2)}, "
            f"P50 {self.calendar.finish_date(round(forecast.p50)).isoformat()}"
        )


def live_page(state: LiveState, language: Language, rows: Sequence[EventRow] = ()) -> str:
    """The cockpit of a live project (module docstring); `rows` is its event log, used to
    rebuild the observation of every recommendation for the risk chart."""
    project = state.project
    if project.baseline is None:
        raise AppError("no_baseline")
    model = project.require_model()
    calendar = project.calendar
    ids = project.activity_ids()
    nodes = project.nodes()
    names = {ids[key]: node.name for key, node in nodes.items()}
    people_by_key = person_names(project)
    people = [people_by_key[key] for key in project.worker_keys()]
    t = LiveText(language, calendar, names, model.role_names, people)
    observation = project.observation()
    gantt_rows_ = _live_rows(project)
    events = _live_events(project)
    forecasts_ = _live_forecasts(state, rows)
    deadline = model.deadline or project.baseline.makespan
    horizon = svg.horizon(
        project.baseline.makespan, deadline, project.day, *(f.p90 for f in forecasts_)
    )
    axis = svg.Axis(horizon)
    lines = [
        svg.VLine(project.baseline.makespan, render("cockpit_plan", language), INK_2, "1.5 2"),
        svg.VLine(deadline, render("cockpit_deadline", language), DEADLINE, "4 2", 1.4),
        svg.VLine(project.day, render("cockpit_today", language), LIVE_COLOR, "", 1.6),
    ]
    gantt = svg.gantt(
        gantt_rows_,
        events,
        axis,
        lines,
        color=LIVE_COLOR,
        key="g1",
        title=render("cockpit_gantt", language),
        t=t,
    )
    risk = svg.risk(
        forecasts_,
        axis,
        deadline=deadline,
        target=sentinel_params(project).theta_d,
        outcomes=[],
        color=LIVE_COLOR,
        key="risk",
        title=render("cockpit_risk", language),
        t=t,
    )
    title = f"{render('cockpit_title', language)}: {project.definition.name}"
    as_of = calendar.date_of(project.day).isoformat()
    kpi_rows = _live_kpis(state, observation.cost, language)
    log_rows = "".join(_log_row(project, entry, language) for entry in state.recommendations)
    head = "".join(
        f'<th scope="col">{escape(render(key, language))}</th>'
        for key in (
            "cockpit_col_date",
            "cockpit_col_action",
            "cockpit_col_p",
            "cockpit_col_reason",
            "cockpit_col_status",
            "cockpit_col_explanation",
        )
    )
    sections = [
        f'<section id="kpis"><h2>{escape(render("cockpit_kpis", language))}</h2>'
        f'<div class="scroll"><table class="kpis"><tbody>{kpi_rows}</tbody></table></div>'
        "</section>",
        f'<section id="gantt"><h2>{escape(render("cockpit_gantt", language))}</h2>'
        f'<p class="note">{escape(render("cockpit_gantt_note", language))}</p>{gantt}</section>',
        f'<section id="risk"><h2>{escape(render("cockpit_risk", language))}</h2>'
        f'<p class="note">{escape(render("cockpit_risk_note", language))}</p>{risk}</section>',
        f'<section id="log"><h2>{escape(render("cockpit_log", language))}</h2>'
        f'<div class="scroll"><table class="log"><thead><tr>{head}</tr></thead>'
        f"<tbody>{log_rows}</tbody></table></div></section>",
        _live_provenance(project, language),
    ]
    header = (
        f'<header><h1>{escape(title)}</h1><p class="subtitle">'
        + escape(render("cockpit_subtitle", language, {"date": as_of}))
        + "</p></header>"
    )
    return (
        "<!doctype html>\n"
        f'<html lang="{language}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"{header}\n<main>\n" + "\n".join(sections) + "\n</main>\n"
        '<div id="tip" role="tooltip" hidden></div>\n'
        f"<script>{SCRIPT}</script>\n</body>\n</html>\n"
    )


def _live_rows(project: LiveProject) -> list[Row]:
    """Baseline bars over the work reported so far, split by the crew's reported absences."""
    assert project.baseline is not None
    ids = project.activity_ids()
    nodes = project.nodes()
    temps = {temp.key for temp in project.temps}
    added = {task.key: task.day for task in project.inserted}
    substitutions: dict[str, list[Substitution]] = {}
    for action in project.actions:
        for op in action.decision.operations:
            if op.kind == "subst":
                key = next(k for k, j in ids.items() if j == op.activity)
                handover = sum(h.added for h in action.handovers if h.task == key) or 1
                substitutions.setdefault(key, []).append(
                    Substitution(
                        day=action.day,
                        activity=op.activity,
                        replaced=(),
                        workers=op.workers,
                        onboarding=max(1, handover // len(op.workers)),
                        handover=handover / nodes[key].unit,
                    )
                )
    rows = []
    for key, tracked in project.tasks.items():
        node = nodes[key]
        segments: list[Segment] = []
        if tracked.start is not None:
            end = tracked.finish if tracked.finish is not None else project.day
            run: tuple[int, int] | None = None  # (first day, present members)
            for day in range(tracked.start, end):
                present = sum(
                    1
                    for member in tracked.crew
                    if member in temps or project.absent(member, day) is None
                )
                if not any(node.demands):
                    present = 1  # a task without a crew progresses every day (spec 3.1 a)
                if run is not None and run[1] == present:
                    continue
                if run is not None and run[1] > 0:
                    segments.append(_segment(run, day, tracked.crew, temps))
                run = (day, present)
            if run is not None and run[1] > 0:
                segments.append(_segment(run, end, tracked.crew, temps))
        start, finish = tracked.start, tracked.finish
        rows.append(
            Row(
                activity=ids[key],
                duration=node.duration,
                demands=node.demands,
                planned=project.baseline.starts.get(key),
                start=start,
                finish=finish,
                segments=tuple(segments),
                paused=_gaps(start, finish if finish is not None else project.day, segments),
                substitutions=tuple(substitutions.get(key, ())),
                shocks=tuple((s.day, s.factor) for s in project.shocks if s.task == key),
                inserted_day=added.get(key),
                descoped_day=tracked.removed,
            )
        )
    return rows


def _segment(run: tuple[int, int], end: int, crew: Sequence[str], temps: set[str]) -> Segment:
    return Segment(run[0], end, run[1], any(member in temps for member in crew))


def _gaps(start: int | None, end: int, segments: Sequence[Segment]) -> tuple[tuple[int, int], ...]:
    if start is None:
        return ()
    gaps, day = [], start
    for segment in sorted(segments, key=lambda s: s.start):
        if segment.start > day:
            gaps.append((day, segment.start))
        day = max(day, segment.end)
    if end > day:
        gaps.append((day, end))
    return tuple(gaps)


def _live_events(project: LiveProject) -> list[DayEvents]:
    """Absence onsets (crew members and idle people), work increases and added tasks by day."""
    ids = project.activity_ids()
    workers = {key: w for w, key in enumerate(project.worker_keys())}
    days: dict[int, dict[str, list[object]]] = {}

    def at(day: int) -> dict[str, list[object]]:
        return days.setdefault(day, {"crew": [], "idle": [], "work": [], "new": []})

    for absence in project.absences:
        crew = next(
            (
                key
                for key, tracked in project.tasks.items()
                if absence.person in tracked.crew
                and tracked.start is not None
                and tracked.start <= absence.start
                and (tracked.finish is None or absence.start < tracked.finish)
            ),
            None,
        )
        if crew is None:
            at(absence.start)["idle"].append(workers[absence.person])
        else:
            at(absence.start)["crew"].append((workers[absence.person], ids[crew]))
    for shock in project.shocks:
        at(shock.day)["work"].append((ids[shock.task], shock.factor))
    for task in project.inserted:
        at(task.day)["new"].append((ids[task.key], task.duration))
    return [
        DayEvents(
            day,
            tuple(days[day]["crew"]),  # type: ignore[arg-type]
            tuple(days[day]["idle"]),  # type: ignore[arg-type]
            tuple(days[day]["work"]),  # type: ignore[arg-type]
            tuple(days[day]["new"]),  # type: ignore[arg-type]
        )
        for day in sorted(days)
    ]


def _live_forecasts(state: LiveState, rows: Sequence[EventRow]) -> list[Forecast]:
    """NOOP's forecast at every recommendation: its rollouts repeated on the recommendation's
    worlds (seed and rollout count of the record), so P(on time) equals the record's."""
    found = []
    for entry in state.recommendations:
        recommendation = entry.recommendation
        impact = recommendation.impact("NOOP")
        if impact is None:
            continue
        before = [row for row in rows if row.seq < entry.seq]
        if not before:
            continue
        project = replay(before).project
        observation = project.observation()
        evaluator = Evaluator(observation, recommendation.seed, sentinel_params(project))
        makespans = evaluator.extend(noop(observation), impact.rollouts).makespan[: impact.rollouts]
        p10, p50, p90 = (float(q) for q in np.quantile(np.asarray(makespans), [0.1, 0.5, 0.9]))
        forecast = Forecast(recommendation.day, impact.rollouts, impact.p_on_time, p10, p50, p90)
        chosen = recommendation.impact(recommendation.record.chosen)
        if recommendation.acts and chosen is not None:
            gate = "auto" if entry.status == "auto" else "escalated"
            forecast = replace(
                forecast,
                chosen=recommendation.record.chosen,
                p_chosen=chosen.p_on_time,
                gate=gate,
            )
        found.append(forecast)
    return found


def _live_kpis(state: LiveState, cost: float, language: Language) -> str:
    project = state.project
    model = project.require_model()
    calendar = project.calendar
    assert project.baseline is not None
    latest = next(
        (e.recommendation for e in reversed(state.recommendations) if e.recommendation.impacts),
        None,
    )
    noop_impact = None if latest is None else latest.impact("NOOP")
    done = sum(t.state == "done" for t in project.tasks.values())
    rows = [
        ("cockpit_kpi_plan", calendar.finish_date(project.baseline.makespan).isoformat()),
        (
            "cockpit_kpi_deadline",
            "—" if project.definition.deadline is None else project.definition.deadline.isoformat(),
        ),
        ("cockpit_kpi_tasks", f"{done} / {len(project.tasks)}"),
        ("cockpit_kpi_cost", f"{cost:.1f} / {model.budget:.1f}"),
    ]
    if noop_impact is not None and noop_impact.mean_makespan is not None:
        finish = calendar.finish_date(int(noop_impact.mean_makespan + 0.5)).isoformat()
        rows.append(("cockpit_kpi_forecast", finish))
        rows.append(("cockpit_kpi_p", f"{noop_impact.p_on_time:.2f}"))
    actions = [e for e in state.recommendations if e.status in ("auto", "approved")]
    rows.append(("cockpit_kpi_actions", str(len(actions))))
    rows.append(("cockpit_kpi_temps", str(len(project.temps))))
    return "".join(
        f'<tr><th scope="row">{escape(render(key, language))}</th><td>{escape(value)}</td></tr>'
        for key, value in rows
    )


def _log_row(project: LiveProject, entry: RecommendationEntry, language: Language) -> str:
    recommendation = entry.recommendation
    record = recommendation.record
    chosen = recommendation.chosen
    decision = chosen.decision if chosen is not None else record.decision
    kind = chosen.kind if chosen is not None else "noop"
    title = describe(decision, kind, project, recommendation.day, language)
    impact = recommendation.impact(record.chosen) or recommendation.impact("NOOP")
    p = "—" if impact is None else f"{impact.p_on_time:.2f}"
    if entry.explanation is not None:
        shown = llm_view(entry.explanation)
        text = shown.text or render("cockpit_llm_invalid", language)
        badge = render(f"cockpit_badge_{shown.badge}", language, {"model": shown.model or "?"})
    else:
        text = template_explanation(record, language).summary
        badge = render("cockpit_badge_template", language)
    date = project.calendar.date_of(recommendation.day).isoformat()
    return (
        f'<tr><td class="num">{escape(date)}</td><td>{escape(title)}</td>'
        f'<td class="num">{escape(p)}</td>'
        f"<td>{escape(render(f'reason_{record.reason}', language))}</td>"
        f"<td>{escape(render(f'status_{entry.status}', language))}</td>"
        f'<td class="expl">{escape(text)}<br><span class="badge">{escape(badge)}</span></td></tr>'
    )


def _live_provenance(project: LiveProject, language: Language) -> str:
    settings = project.definition.settings
    git = git_state(GIT_EXCLUDE)
    pert = settings.pert()
    disruptions = settings.disruption_params()
    try:
        app_version = version("sentinel")
    except PackageNotFoundError:  # pragma: no cover - installed with the project
        app_version = "?"
    rows = [
        ("cockpit_p_software", f"Sentinel {app_version}, commit {git['commit'] or '?'}"),
        (
            "cockpit_p_settings",
            f"PERT ({pert.a:g}, {pert.m:g}, {pert.b:g}), lambda_A {disruptions.lambda_a:g}, "
            f"lambda_S {disruptions.lambda_s:g}, lambda_N {disruptions.lambda_n:g}, "
            f"E[L] {disruptions.mean_absence:g}, autonomy {settings.autonomy}, "
            f"seed {settings.seed}",
        ),
        ("cockpit_p_note", render("cockpit_p_note_text", language)),
    ]
    body = "".join(
        f'<tr><th scope="row">{escape(render(key, language))}</th><td>{escape(value)}</td></tr>'
        for key, value in rows
    )
    return (
        f'<section id="provenance"><h2>{escape(render("cockpit_provenance", language))}</h2>'
        f'<div class="scroll"><table class="prov"><tbody>{body}</tbody></table></div></section>'
    )
