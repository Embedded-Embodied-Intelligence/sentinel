"""The simulator (WP9b; spec section 11.6): an example project with a hidden world, run day by
day under Sentinel or with nobody reacting, a timeline of what happened and what Sentinel did,
and at the end the comparison with nobody reacting on the same events (common random numbers).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.agent.decide import DecisionRecord
from sentinel.app.errors import AppError
from sentinel.app.messages import render
from sentinel.app.simulator import PolicyRun, Simulation, SimulatorSpec
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form
from sentinel.app.ui.pages import job_progress
from sentinel.app.ui.text import Texts
from sentinel.interpret.team import names_of
from sentinel.policies.base import Decision, Descope, Overtime, Reseq, Shift, Subst
from sentinel.simulation.events import Absence, NewActivity, WorkIncrease
from sentinel.simulation.state import Observation, worker_roles


@dataclass(frozen=True)
class Example:
    """An example project of the simulator: a world of the WP8 cockpits (docs/dashboard)."""

    key: str
    size: str
    set_name: str
    instance: str
    scenario: int


EXAMPLES = (
    Example("small", "j30", "j30", "j3026_7", 1),
    Example("medium", "j60", "j60", "j6010_7", 1),
)
END = 10_000  # "to the end": more days than any run lasts


@dataclass(frozen=True)
class Entry:
    """A line of the simulator's timeline."""

    day: int
    order: int
    kind: str  # absence, grows, new, sentinel, finish
    when: str
    text: str


def describe(
    decision: Decision,
    kind: str,
    observation: Observation | None,
    tasks: dict[int, str],
    people: Sequence[str],
    roles: Sequence[str],
    texts: Texts,
) -> str:
    """A simulator decision in the wording of spec section 11.7 (as `views.describe`)."""
    language = texts.lang
    if not decision.operations:
        return render("action_noop", language)
    parts = []
    plan_part = None
    for op in decision.operations:
        match op:
            case Subst():
                task = tasks.get(op.activity, str(op.activity))
                for worker, absent in _pairs(op, observation):
                    values = {
                        "worker": _person(worker, people, observation, roles, texts),
                        "absent": "?"
                        if absent is None
                        else _person(absent, people, observation, roles, texts),
                        "task": task,
                    }
                    parts.append(render("action_subst", language, values))
            case Overtime():
                code = "action_overtime_one" if op.workers == 1 else "action_overtime_many"
                hire = {"count": op.workers, "role": roles[op.role], "days": op.days}
                parts.append(render(code, language, hire))
            case Descope():
                parts.append(
                    render("action_descope", language, {"task": tasks.get(op.activity, "?")})
                )
            case Shift():
                plan_part = render("action_shift", language)
            case Reseq():
                stable = kind.endswith("reseq_s")
                plan_part = render("action_reseq_s" if stable else "action_reseq_m", language)
    if plan_part is not None:
        parts.append(plan_part)
    first, *rest = parts
    return render("action_then", language).join([first, *(p[:1].lower() + p[1:] for p in rest)])


def _pairs(op: Subst, observation: Observation | None) -> list[tuple[int, int | None]]:
    """(substitute, replaced member) of a SUBST on the observation it was decided on (spec 4)."""
    if observation is None:
        return [(w, None) for w in op.workers]
    roles = worker_roles(observation)
    crew = observation.assigned[op.activity] if op.activity < len(observation.assigned) else ()
    absent = sorted(w for w in crew if not observation.present[w])
    pairs: list[tuple[int, int | None]] = []
    for w in op.workers:
        match = next((a for a in absent if roles[a] == roles[w]), None)
        if match is not None:
            absent.remove(match)
        pairs.append((w, match))
    return pairs


def _person(
    w: int,
    people: Sequence[str],
    observation: Observation | None,
    roles: Sequence[str],
    texts: Texts,
) -> str:
    if w < len(people):
        return people[w]
    role = 0
    number = 1
    if observation is not None:
        temps = observation.temporary
        index = w - len(people)
        if index < len(temps):
            role = temps[index].role
            number = 1 + sum(1 for temp in temps[:index] if temp.role == role)
    return render("temporary_person", texts.lang, {"role": roles[role], "number": number})


def timeline(run: PolicyRun, texts: Texts) -> list[Entry]:
    """What happened in the run so far and what Sentinel did, newest first."""
    world = run.world
    calendar = world.calendar
    state = run.state
    tasks = names_of(state.observe(), world.spec.names_seed)
    people = list(world.people)
    roles = list(world.roles)
    entries: list[Entry] = []
    for event in run.run.events or ():
        when = texts.date(calendar.date_of(event.day))
        match event:
            case Absence():
                text = texts.plural(
                    "sim.event.away",
                    event.announced,
                    person=_person(event.worker, people, None, roles, texts),
                )
                entries.append(Entry(event.day, 0, "absence", when, text))
            case WorkIncrease():
                percent = round(100 * (event.factor - 1))
                name = tasks.get(event.activity, str(event.activity))
                entries.append(
                    Entry(
                        event.day,
                        1,
                        "grows",
                        when,
                        texts("sim.event.grows", task=name, percent=percent),
                    )
                )
            case NewActivity():
                name = tasks.get(event.activity, str(event.activity))
                text = texts.plural("sim.event.new", event.duration, task=name)
                entries.append(Entry(event.day, 2, "new", when, text))
    sentinel = run.sentinel
    observations = run.observations
    if sentinel is not None:
        for record in sentinel.records:
            entry = _decision_entry(
                record,
                observations.get(record.day),
                tasks,
                people,
                roles,
                texts,
                calendar.date_of(record.day),
            )
            if entry is not None:
                entries.append(entry)
    if run.finished:
        result = run.result()
        finish = calendar.finish_date(result.makespan)
        late = max(0, result.makespan - world.deadline)
        text = (
            texts("sim.event.finished", date=texts.date(finish))
            + " "
            + (
                texts("sim.on_time")
                if late == 0 and not result.truncated
                else texts.plural("sim.late", late)
            )
        )
        entries.append(Entry(result.makespan, 9, "finish", texts.date(finish), text))
    entries.sort(key=lambda e: (e.day, e.order), reverse=True)
    return entries


def _decision_entry(
    record: DecisionRecord,
    observation: Observation | None,
    tasks: dict[int, str],
    people: Sequence[str],
    roles: Sequence[str],
    texts: Texts,
    day: date,
) -> Entry | None:
    when = texts.date(day)
    chosen = next((c for c in record.candidates if c.label == record.chosen), None)
    if record.reason == "approved" and record.decision.operations:
        text = describe(
            record.decision, chosen.kind if chosen else "", observation, tasks, people, roles, texts
        )
        return Entry(record.day, 4, "sentinel", when, texts("sim.event.approved", action=text))
    if not record.deliberated or record.chosen == "NOOP" or chosen is None:
        return None
    text = describe(chosen.decision, chosen.kind, observation, tasks, people, roles, texts)
    if record.gate == "auto":
        return Entry(record.day, 3, "sentinel", when, texts("sim.event.auto", action=text))
    if record.gate == "escalated":
        return Entry(record.day, 3, "sentinel", when, texts("sim.event.asked", action=text))
    if record.gate == "deferred":
        return Entry(record.day, 3, "sentinel", when, texts("sim.event.deferred", action=text))
    return None


def verdict(sides: Sequence[object], texts: Texts) -> str:
    """The comparison of a finished run with nobody reacting, in one sentence."""
    from sentinel.app.simulator import SimSide

    runs = [s for s in sides if isinstance(s, SimSide)]
    main = runs[0]
    if len(runs) == 1 or main.finish is None:
        if main.on_time:
            return texts("sim.verdict.single_on_time")
        return texts.plural("sim.verdict.single_late", main.late_days or 0)
    other = runs[1]
    if main.on_time and other.on_time:
        return texts("sim.verdict.both_on_time")
    if main.on_time:
        return texts.plural("sim.verdict.saved", other.late_days or 0)
    if other.on_time:
        return texts.plural("sim.verdict.worse", main.late_days or 0)
    return texts("sim.verdict.both_late", main=main.late_days or 0, other=other.late_days or 0)


def simulation_page(ui: Ui, request: Request, project_id: str) -> Response:
    services = ui.services
    session = ui.session(request)
    texts = ui.texts(request)
    view = services.simulator(session, project_id)

    def build(simulation: Simulation) -> list[Entry]:
        return timeline(simulation.main, texts)

    entries = services.with_simulation(session, project_id, build)
    sides = [view.main] + ([view.compare] if view.compare is not None else [])
    running = services.store.project_jobs(session, project_id)
    return ui.page(
        request,
        "simulation.html",
        title=view.name,
        nav="simulator",
        sim=view,
        sides=sides,
        timeline=entries[:200],
        verdict=verdict(sides, texts) if view.finished else "",
        continue_run=request.query_params.get("run") == "end" and not running,
    )


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    @routes.get("/simulator")
    def setup(request: Request) -> Response:
        available = [e for e in EXAMPLES if e.instance in services.instances(e.set_name)]
        return ui.page(
            request,
            "simulator.html",
            title=ui.texts(request)("sim.title"),
            nav="simulator",
            examples=available,
            available=bool(available),
        )

    @routes.post("/simulator")
    async def create(request: Request) -> Response:
        form = await Form.read(request)
        example = next((e for e in EXAMPLES if e.key == form.get("example")), EXAMPLES[0])
        disruptions = form.get("disruptions", "typical")
        policy = form.get("policy", "sentinel")
        if disruptions not in ("calm", "typical", "turbulent") or policy not in (
            "sentinel",
            "no_reaction",
        ):
            raise AppError("invalid_request")
        texts = ui.texts(request)
        spec = SimulatorSpec(
            name=texts(f"sim.name.{example.size}"),
            set_name=example.set_name,  # type: ignore[arg-type]
            instance=example.instance,
            scenario=example.scenario,
            start=date.today(),
            disruptions=disruptions,  # type: ignore[arg-type]
            policy=policy,  # type: ignore[arg-type]
        )
        job = services.create_simulator(ui.session(request), spec, ui.language(request))
        return job_progress(ui, request, job, "job.simulator")

    @routes.post("/projects/{project_id}/advance")
    async def advance(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        choice = form.get("days", "1")
        if choice == "end":
            limit = ui.config.limits.simulator_days if ui.config.demo else None
            days = limit or END
            target = f"/projects/{project_id}?run=end"
        elif choice in ("1", "5", "10"):
            days = int(choice)
            target = f"/projects/{project_id}"
        else:
            raise AppError("invalid_request")
        job = services.advance(ui.session(request), project_id, days, ui.language(request))
        return job_progress(ui, request, job, "job.advance", next=target)

    return routes
