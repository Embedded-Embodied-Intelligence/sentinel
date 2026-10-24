"""The application's services (WP9a; spec section 11), without any HTTP: live projects
(create, import, edit, plan, forecast, check in, recommend, decide, explain, export), simulator
projects (create, advance, compare), task extraction from text and cockpit exports.

Every operation names the session that owns the project, and the store refuses another
session's data. A project's state is rebuilt from its event log (`events.replay`) and kept in a
small cache keyed by the log's last sequence number; writes to one project are serialised by a
lock per project. Long operations run as background jobs (`jobs.JobRunner`) whose results are
deterministic for the project's seed. Limits of the demo mode (projects per session, tasks per
project, simulator days, concurrent jobs) are checked here; request rates and CSRF tokens in the
web layer (ADR-0024).
"""

import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.app import io, planning, simulator
from sentinel.app.config import AppConfig
from sentinel.app.errors import AppError
from sentinel.app.events import (
    BaselineSet,
    CheckinDone,
    Created,
    Decided,
    DefinitionChanged,
    Explained,
    LiveState,
    Recommended,
    Source,
    Verdict,
    replay,
)
from sentinel.app.jobs import JobRunner, Progress
from sentinel.app.live import (
    Issue,
    LiveError,
    LiveProject,
    build_model,
    errors,
    validate_definition,
)
from sentinel.app.llm import ClientFactory, LlmService, make_client
from sentinel.app.messages import render
from sentinel.app.models import CheckIn, Language, Person, ProjectDefinition, Settings, Task
from sentinel.app.store import (
    LOCAL_SESSION,
    EventRow,
    JobRow,
    ProjectRow,
    SessionRow,
    Store,
    now,
)
from sentinel.app.views import (
    IssueView,
    ProjectSummary,
    ProjectView,
    forecast_view,
    issue_views,
    person_names,
    project_view,
)
from sentinel.experiments.runs import derive_seed
from sentinel.policies.sentinel import Proposer
from sentinel.simulation.state import Observation
from sentinel.wbs.extract import Extraction

SIMULATIONS_KEPT = 8  # simulator projects kept in memory; others are re-simulated


class ErrorView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    details: list[IssueView] = []


class JobView(BaseModel):
    """A background job: its state, progress and, when done, its result or error."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str
    project: str | None
    status: Literal["queued", "running", "done", "failed"]
    progress: float
    message: str
    result: dict[str, Any] | None = None
    error: ErrorView | None = None


class EventView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int
    type: str
    created: datetime


class CheckinResult(BaseModel):
    """A check-in applied: the project now, and the job of the recommendation that follows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project: ProjectView
    recommendation_job: JobView | None


def error_view(error: AppError, language: Language) -> ErrorView:
    return ErrorView(
        code=error.code,
        message=render(error.code, language, error.params),
        details=issue_views(error.issues, language),
    )


def stored_error_view(payload: Mapping[str, Any], language: Language) -> ErrorView:
    """A job's stored error in a language."""
    issues = [
        Issue(
            i["code"],
            tuple(i.get("params", {}).items()),
            i.get("where"),
            i.get("severity", "error"),
        )
        for i in payload.get("issues", [])
    ]
    code = str(payload.get("code", "internal_error"))
    return ErrorView(
        code=code,
        message=render(code, language, payload.get("params", {})),
        details=issue_views(issues, language),
    )


def job_view(job: JobRow, language: Language) -> JobView:
    return JobView(
        id=job.id,
        kind=job.kind,
        project=job.project,
        status=job.status,
        progress=job.progress,
        message=job.message,
        result=job.result if job.status == "done" else None,
        error=None if job.error is None else stored_error_view(job.error, language),
    )


class Services:
    """The services of one server."""

    def __init__(self, config: AppConfig, *, llm_factory: ClientFactory | None = None) -> None:
        self.config = config
        self.limits = config.limits
        self.store = Store(config.database)
        self.store.fail_unfinished_jobs()
        self.jobs = JobRunner(self.store, workers=config.workers, inline=config.inline_jobs)
        self.llm = LlmService(
            config.settings_file,
            config.llm_cache,
            self.store,
            mode=config.llm,
            daily_cap=config.limits.llm_calls_per_day,
            factory=llm_factory or make_client,
        )
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}
        self._live: OrderedDict[str, tuple[int, LiveState]] = OrderedDict()
        self._sims: OrderedDict[str, tuple[int, simulator.Simulation]] = OrderedDict()
        self.showcase: Callable[[str], None] | None = None  # set by the web layer (demo)

    def close(self) -> None:
        self.jobs.shutdown()

    # ---- sessions

    def local_session(self) -> SessionRow:
        return self.store.ensure_session(LOCAL_SESSION, demo=False)

    def new_session(self) -> SessionRow:
        """A new demo sandbox, with the showcase project if configured."""
        session = self.store.create_session(demo=True)
        if self.showcase is not None:
            self.showcase(session.id)
        return session

    def expire_sandboxes(self) -> int:
        before = now() - timedelta(hours=self.limits.sandbox_hours)
        return self.store.expire(before)

    # ---- helpers

    @contextmanager
    def _lock(self, project_id: str) -> Iterator[None]:
        with self._guard:
            lock = self._locks.setdefault(project_id, threading.RLock())
        with lock:
            yield

    def _row(self, session: str, project_id: str) -> ProjectRow:
        row = self.store.project(session, project_id)
        if row is None:
            raise AppError("project_not_found", "not_found")
        return row

    def _state(self, session: str, project_id: str) -> tuple[ProjectRow, LiveState]:
        """The live project, rebuilt from its log or taken from the cache."""
        row = self._row(session, project_id)
        if row.kind != "live":
            raise AppError("not_a_live_project", "invalid")
        with self._guard:
            cached = self._live.get(project_id)
            if cached is not None and cached[0] == row.seq:
                self._live.move_to_end(project_id)
                return row, _copy(cached[1])
        state = replay(self.store.events(session, project_id))
        with self._guard:
            self._live[project_id] = (state.seq, state)
            while len(self._live) > 64:
                self._live.popitem(last=False)
        return row, _copy(state)

    def _append(
        self,
        session: str,
        row: ProjectRow,
        event_type: str,
        event: BaseModel,
        *,
        expected: int | None = None,
        name: str | None = None,
    ) -> int:
        payload = event.model_dump(mode="json")
        return self.store.append(
            session,
            row.id,
            event_type,
            payload,
            expected=row.seq if expected is None else expected,
            name=name,
        )

    def _check_tasks(self, definition: ProjectDefinition, extra: int = 0) -> None:
        limit = self.limits.tasks_per_project
        if self.config.demo and limit is not None and len(definition.tasks) + extra > limit:
            raise AppError("limit_tasks", "limit", limit=limit)

    def _check_projects(self, session: str) -> None:
        limit = self.limits.projects_per_session
        if self.config.demo and limit is not None and self.store.count_projects(session) >= limit:
            raise AppError("limit_projects", "limit", limit=limit)

    def _submit(
        self,
        session: str,
        project: str | None,
        kind: str,
        work: Callable[[Progress], Mapping[str, Any]],
        language: Language,
    ) -> JobView:
        limit = self.limits.concurrent_jobs
        if self.config.demo and limit is not None and self.store.active_jobs(session) >= limit:
            raise AppError("limit_jobs", "limit")
        return job_view(self.jobs.submit(session, project, kind, work), language)

    # ---- projects

    def projects(self, session: str) -> list[ProjectSummary]:
        return [
            ProjectSummary(id=r.id, kind=r.kind, name=r.name, created=r.created, updated=r.updated)
            for r in self.store.projects(session)
        ]

    def project(self, session: str, project_id: str, language: Language) -> BaseModel:
        """A live project's view, or a simulator project's."""
        row = self._row(session, project_id)
        if row.kind == "simulator":
            return self.simulator(session, project_id)
        _, state = self._state(session, project_id)
        return project_view(row.id, state, language, row.name)

    def validate(self, definition: ProjectDefinition, language: Language) -> list[IssueView]:
        return issue_views(validate_definition(definition), language)

    def live(self, session: str, project_id: str, language: Language) -> ProjectView:
        """A live project's view (spec section 11)."""
        row, state = self._state(session, project_id)
        return project_view(row.id, state, language, row.name)

    def create(
        self,
        session: str,
        definition: ProjectDefinition,
        language: Language,
        source: Source = "new",
    ) -> ProjectView:
        self._check_projects(session)
        self._check_tasks(definition)
        event = Created(definition=definition, source=source)
        row = self.store.create_project(
            session, "live", definition.name or "project", "created", event.model_dump(mode="json")
        )
        return self.live(session, row.id, language)

    def update_definition(
        self, session: str, project_id: str, definition: ProjectDefinition, language: Language
    ) -> ProjectView:
        self._check_tasks(definition)
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            try:
                state.project.set_definition(definition)
            except LiveError as exc:
                raise AppError.of(exc) from exc
            self._append(
                session,
                row,
                "definition",
                DefinitionChanged(definition=definition),
                name=definition.name or row.name,
            )
        return self.live(session, project_id, language)

    def delete(self, session: str, project_id: str) -> None:
        with self._lock(project_id):
            if not self.store.delete_project(session, project_id):
                raise AppError("project_not_found", "not_found")
            with self._guard:
                self._live.pop(project_id, None)
                self._sims.pop(project_id, None)

    def events(self, session: str, project_id: str) -> list[EventView]:
        self._row(session, project_id)
        return [
            EventView(seq=e.seq, type=e.type, created=e.created)
            for e in self.store.events(session, project_id)
        ]

    # ---- plan, forecast, check-ins, recommendations, decisions

    def plan(self, session: str, project_id: str, language: Language) -> JobView:
        """Build the baseline plan (spec section 11.3) in a job."""
        _, state = self._state(session, project_id)
        project = state.project
        if project.tracking:
            raise AppError("structure_frozen", "conflict")
        found = errors(_validate(project.definition))
        if found:
            raise AppError(found[0].code, "invalid", found, **found[0].values)

        def work(progress: Progress) -> Mapping[str, Any]:
            with self._lock(project_id):
                row, state = self._state(session, project_id)
                if state.project.tracking:
                    raise AppError("structure_frozen", "conflict")
                progress(0.1, "planning")
                baseline = planning.baseline_plan(build_model(state.project.definition))
                self._append(session, row, "baseline", BaselineSet(baseline=baseline))
                return baseline.model_dump(mode="json")

        return self._submit(session, project_id, "plan", work, language)

    def forecast(self, session: str, project_id: str, language: Language) -> JobView:
        """The forecast of spec section 11.4 in a job (not stored in the log)."""
        _, state = self._state(session, project_id)
        _ready(state.project)

        def work(progress: Progress) -> Mapping[str, Any]:
            _, current = self._state(session, project_id)
            progress(0.05, "simulating")
            result = planning.forecast(current.project)
            return forecast_view(current.project, result).model_dump(mode="json")

        return self._submit(session, project_id, "forecast", work, language)

    def checkin(
        self, session: str, project_id: str, checkin: CheckIn, language: Language
    ) -> CheckinResult:
        """Apply a check-in (spec section 11.3); a recommendation job follows (11.5)."""
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            project = state.project
            _ready(project, need_deadline=False)
            limit = self.limits.tasks_per_project
            added = len(project.tasks) + len(checkin.new_tasks)
            if self.config.demo and limit is not None and added > limit:
                raise AppError("limit_tasks", "limit", limit=limit)
            try:
                effects = project.resolve_checkin(checkin)
            except LiveError as exc:
                raise AppError.of(exc) from exc
            self._append(session, row, "checkin", CheckinDone(checkin=checkin, effects=effects))
        job = None
        _, state = self._state(session, project_id)
        if state.project.definition.deadline is not None and not state.project.finished:
            try:
                job = self.recommend(session, project_id, language)
            except AppError:
                job = None  # e.g. the job limit; the manager can ask again
        return CheckinResult(
            project=self.live(session, project_id, language), recommendation_job=job
        )

    def recommend(self, session: str, project_id: str, language: Language) -> JobView:
        """A Sentinel deliberation on the latest observation in a job (spec section 11.5)."""
        _, state = self._state(session, project_id)
        _ready(state.project)

        def work(progress: Progress) -> Mapping[str, Any]:
            with self._lock(project_id):
                row, current = self._state(session, project_id)
                project = current.project
                _ready(project)
                progress(0.05, "deliberating")
                recommendation = planning.recommend(project, proposer=self._proposer(project))
                applied = None
                record = recommendation.record
                if record.gate == "auto" and recommendation.chosen is not None:
                    outcome = project.resolve_action(
                        record.decision, record.chosen, recommendation.chosen.kind
                    )
                    if isinstance(outcome, str):  # pragma: no cover - validated by the agent
                        raise RuntimeError(f"an automatic action was rejected: {outcome}")
                    applied = outcome
                seq = self._append(
                    session,
                    row,
                    "recommendation",
                    Recommended(recommendation=recommendation, applied=applied),
                )
                return {"recommendation": seq}

        return self._submit(session, project_id, "recommend", work, language)

    def _proposer(self, project: LiveProject) -> Proposer | None:
        """The LLM's proposals (spec section 10.3) if the project asks for them (off by
        default, spec section 11.5) and a model is set up; one call per deliberation that
        passed the needs gate, through the cache without prompts."""
        settings = project.definition.settings
        if not settings.llm_proposals or not self.llm.available:
            return None
        ids = project.activity_ids()
        names = {ids[key]: node.name for key, node in project.nodes().items()}
        roles = project.require_model().role_names
        params = planning.sentinel_params(project)
        llm = self.llm

        def propose(
            observation: Observation, record: DecisionRecord, rule: Sequence[Candidate]
        ) -> Sequence[Candidate]:
            seed = derive_seed(settings.seed, "llm", "proposals", str(observation.day))
            return llm.propose(observation, record, rule, names, roles, params, seed)

        return propose

    def decide(
        self, session: str, project_id: str, seq: int, verdict: Verdict, language: Language
    ) -> ProjectView:
        """The manager's decision on a recommendation (spec section 11.5)."""
        follow = False
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            entry = state.recommendation(seq)
            if entry is None:
                raise AppError("recommendation_not_found", "not_found")
            if entry.status not in ("open", "later"):
                status = render(f"status_{entry.status}", language)
                raise AppError("recommendation_closed", "conflict", status=status)
            project = state.project
            event = Decided(recommendation=seq, verdict=verdict)
            if verdict == "approve":
                try:
                    approved, rejection = planning.approval(project, entry.recommendation)
                except LiveError as exc:
                    raise AppError.of(exc) from exc
                outcome: Any = rejection
                if rejection is None:
                    outcome = project.resolve_action(
                        approved.decision, approved.label, approved.kind
                    )
                if isinstance(outcome, str):
                    event = Decided(recommendation=seq, verdict=verdict, discarded=outcome)
                    follow = True
                else:
                    event = Decided(recommendation=seq, verdict=verdict, applied=outcome)
            self._append(session, row, "decision", event)
        if follow:
            with suppress(AppError):  # e.g. the job limit; the manager can ask again
                self.recommend(session, project_id, language)
        return self.live(session, project_id, language)

    def explain(self, session: str, project_id: str, seq: int, language: Language) -> JobView:
        """An LLM explanation of a recommendation with its faithfulness badge (spec 10.4)."""
        _, state = self._state(session, project_id)
        entry = state.recommendation(seq)
        if entry is None:
            raise AppError("recommendation_not_found", "not_found")
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")

        def work(progress: Progress) -> Mapping[str, Any]:
            with self._lock(project_id):
                row, current = self._state(session, project_id)
                found = current.recommendation(seq)
                assert found is not None
                before = [e for e in self.store.events(session, project_id) if e.seq < seq]
                observation = replay(before).project.observation()
                project = current.project
                roles = project.require_model().role_names
                record = found.recommendation.record
                key = derive_seed(project.definition.settings.seed, "llm", "explain", str(seq))
                explanation = self.llm.explain(
                    record, observation, planning.sentinel_params(project), roles, key
                )
                self._append(
                    session,
                    row,
                    "explanation",
                    Explained(recommendation=seq, explanation=explanation),
                )
                return explanation.model_dump(mode="json")

        return self._submit(session, project_id, "explain", work, language)

    # ---- import and export

    def import_csv(
        self,
        session: str,
        tasks_csv: bytes,
        team_csv: bytes | None,
        *,
        name: str,
        start: date,
        deadline: date | None,
        budget: float | None,
        language: Language,
    ) -> ProjectView:
        definition = io.definition_from_csv(
            tasks_csv,
            team_csv,
            name=name,
            start=start,
            deadline=deadline,
            budget=budget,
            settings=Settings(language=language),
        )
        return self.create(session, definition, language, "csv")

    def import_json(self, session: str, data: Any, language: Language) -> BaseModel:
        """A project from its JSON export, checked by replaying its log."""
        kind, name, events = io.read_export(data)
        self._check_projects(session)
        if kind == "live":
            rows = [_row_of(i + 1, t, p) for i, (t, p) in enumerate(events)]
            try:
                state = replay(rows)
                if state.project.baseline is not None:
                    state.project.check()  # the state must be one the engine could be in
            except (ValueError, ValidationError, LiveError, KeyError, IndexError) as exc:
                raise AppError("json_invalid", detail=type(exc).__name__) from exc
            self._check_tasks(state.project.definition, len(state.project.inserted))
            first = Created.model_validate(events[0][1]).model_copy(update={"source": "json"})
            row = self.store.create_project(
                session, "live", name, "created", first.model_dump(mode="json")
            )
        else:
            spec = _simulator_spec(events)
            self._check_simulator(spec)
            row = self.store.create_project(
                session, "simulator", name, "simulator", {"spec": spec.model_dump(mode="json")}
            )
        for event_type, payload in events[1:]:
            self.store.append(session, row.id, event_type, payload)
        return self.project(session, row.id, language)

    def export(self, session: str, project_id: str) -> dict[str, Any]:
        row = self._row(session, project_id)
        return io.export_project(row.kind, row.name, self.store.events(session, project_id))

    def plan_csv(self, session: str, project_id: str) -> str:
        _, state = self._state(session, project_id)
        project = state.project
        if project.baseline is None:
            raise AppError("no_baseline")
        return io.plan_csv(project, person_names(project))

    def extract(self, session: str, text: str, language: Language) -> JobView:
        """Tasks and team read from a description by the LLM (WP6a extraction with repair
        rounds); the draft is returned for review, not saved."""
        if not text.strip():
            raise AppError("text_empty")
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")
        seed = derive_seed(2026, "llm", "extract", text)

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.05, "reading")
            found = self.llm.extract(text, seed)
            final = found.final
            if final.response.value is None:
                detail = (
                    "no valid answer" if final.response.error is None else final.response.error.kind
                )
                raise AppError("extraction_failed", "invalid", detail=detail)
            draft = draft_definition(final.response.value, now().date(), language)
            return {
                "definition": draft.model_dump(mode="json"),
                "rounds": len(found.rounds),
                "issues": len(final.issues),
            }

        return self._submit(session, None, "extract", work, language)

    # ---- simulator

    def instances(self, set_name: str) -> list[str]:
        return simulator.available(set_name, self.config.psplib_root)

    def _check_simulator(self, spec: simulator.SimulatorSpec) -> None:
        if spec.instance not in self.instances(spec.set_name):
            if not self.instances(spec.set_name):
                raise AppError("psplib_missing", "unavailable")
            raise AppError("unknown_instance", "not_found", instance=spec.instance)
        limit = self.limits.tasks_per_project
        n_real = 30 if spec.set_name == "j30" else 60
        if self.config.demo and limit is not None and n_real > limit:
            raise AppError("limit_tasks", "limit", limit=limit)

    def create_simulator(
        self, session: str, spec: simulator.SimulatorSpec, language: Language
    ) -> JobView:
        """A simulator project; its world (baseline plan, C*) is prepared in a job."""
        self._check_projects(session)
        self._check_simulator(spec)
        name = spec.name or f"{spec.set_name}/{spec.instance}"
        row = self.store.create_project(
            session, "simulator", name, "simulator", {"spec": spec.model_dump(mode="json")}
        )

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.05, "preparing")
            return self.simulator(session, row.id).model_dump(mode="json")

        return self._submit(session, row.id, "simulator", work, language)

    def _simulation(self, session: str, project_id: str) -> tuple[ProjectRow, simulator.Simulation]:
        row = self._row(session, project_id)
        if row.kind != "simulator":
            raise AppError("not_a_simulator", "invalid")
        with self._guard:
            cached = self._sims.get(project_id)
            if cached is not None and cached[0] == row.seq:
                self._sims.move_to_end(project_id)
                return row, cached[1]
        events = self.store.events(session, project_id)
        spec = _simulator_spec([(e.type, e.payload) for e in events])
        try:
            world = simulator.build_world(spec, self.config.psplib_root, self.config.baseline_cache)
        except FileNotFoundError as exc:
            raise AppError("psplib_missing", "unavailable") from exc
        simulation = simulator.Simulation(world)
        for event in events[1:]:
            if event.type == "advance":
                simulation.advance(int(event.payload["days"]))
        with self._guard:
            self._sims[project_id] = (row.seq, simulation)
            while len(self._sims) > SIMULATIONS_KEPT:
                self._sims.popitem(last=False)
        return row, simulation

    def simulator(self, session: str, project_id: str) -> simulator.SimulatorView:
        with self._lock(project_id):
            row, simulation = self._simulation(session, project_id)
            return simulator.simulator_view(row.id, row.seq, simulation)

    def advance(self, session: str, project_id: str, days: int, language: Language) -> JobView:
        """Advance a simulator project by `days` days in a job (spec section 11.6)."""
        limit = self.limits.simulator_days
        if self.config.demo and limit is not None and days > limit:
            raise AppError("limit_days", "limit", limit=limit)
        if days < 1:
            raise AppError("field_invalid", field="days", detail="at least 1")
        row = self._row(session, project_id)
        if row.kind != "simulator":
            raise AppError("not_a_simulator", "invalid")

        def work(progress: Progress) -> Mapping[str, Any]:
            with self._lock(project_id):
                row, simulation = self._simulation(session, project_id)
                if simulation.finished:
                    raise AppError("simulation_finished", "conflict")
                moved = simulation.advance(days, lambda f: progress(f, "simulating"))
                seq = self.store.append(
                    session, project_id, "advance", {"days": moved}, expected=row.seq
                )
                with self._guard:
                    self._sims[project_id] = (seq, simulation)
                return simulator.simulator_view(project_id, seq, simulation).model_dump(mode="json")

        return self._submit(session, project_id, "advance", work, language)

    # ---- cockpit

    def cockpit(self, session: str, project_id: str, language: Language) -> JobView:
        """The cockpit HTML of WP8 for the project, in a job (`cockpit`)."""
        from sentinel.app import cockpit

        row = self._row(session, project_id)

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.05, "writing")
            if row.kind == "simulator":
                with self._lock(project_id):
                    _, simulation = self._simulation(session, project_id)
                    if not simulation.finished:
                        raise AppError("simulation_running", "conflict")
                    html = cockpit.simulator_page(simulation, language)
            else:
                _, state = self._state(session, project_id)
                rows = self.store.events(session, project_id)
                html = cockpit.live_page(state, language, rows)
            return {"html": html}

        return self._submit(session, project_id, "cockpit", work, language)

    # ---- jobs

    def job(self, session: str, job_id: str, language: Language) -> JobView:
        job = self.store.job(session, job_id)
        if job is None:
            raise AppError("job_not_found", "not_found")
        return job_view(job, language)

    def job_row(self, session: str, job_id: str) -> JobRow:
        job = self.store.job(session, job_id)
        if job is None:
            raise AppError("job_not_found", "not_found")
        return job


def _validate(definition: ProjectDefinition) -> list[Issue]:
    return validate_definition(definition)


def _ready(project: LiveProject, *, need_deadline: bool = True) -> None:
    """Refuse an operation on a project without a valid definition, a plan or a deadline."""
    found = errors(_validate(project.definition))
    if found:
        raise AppError(found[0].code, "invalid", found, **found[0].values)
    if project.baseline is None:
        raise AppError("no_baseline")
    if need_deadline and project.definition.deadline is None:
        raise AppError("no_deadline")
    if need_deadline and project.finished:
        raise AppError("project_finished", "conflict")


def _copy(state: LiveState) -> LiveState:
    """A copy of a cached state that an operation may change."""
    return LiveState(state.project.copy(), state.source, state.seq, [*state.recommendations])


def _row_of(seq: int, event_type: str, payload: dict[str, Any]) -> EventRow:
    return EventRow("import", seq, event_type, payload, now())


def _simulator_spec(events: list[tuple[str, dict[str, Any]]]) -> simulator.SimulatorSpec:
    if not events or events[0][0] != "simulator":
        raise AppError("json_invalid", detail="not a simulator project")
    try:
        spec = simulator.SimulatorSpec.model_validate(events[0][1].get("spec"))
    except ValidationError as exc:
        raise AppError("json_invalid", detail="the simulator settings are not valid") from exc
    for event_type, payload in events[1:]:
        days = payload.get("days")
        if event_type != "advance" or not isinstance(days, int) or days < 0:
            raise AppError("json_invalid", detail="unexpected simulator event")
    return spec


def draft_definition(extraction: Extraction, start: date, language: Language) -> ProjectDefinition:
    """A definition from an extraction (WP6a) for the manager to review: people named after
    their role ("Tester 1"), tasks T1, T2, ... with predecessors by key."""
    people: list[Person] = []
    for member in extraction.team:
        for i in range(max(0, member.count)):
            people.append(
                Person(key=f"P{len(people) + 1}", name=f"{member.role} {i + 1}", role=member.role)
            )
    keys = {a.name: f"T{i + 1}" for i, a in enumerate(extraction.activities)}
    tasks = tuple(
        Task(
            key=keys[a.name],
            name=a.name,
            duration=a.duration_days,
            crew=dict(a.crew),
            predecessors=tuple(keys.get(p, p) for p in a.predecessors),
        )
        for a in extraction.activities
    )
    return ProjectDefinition(
        name="", start=start, team=tuple(people), tasks=tasks, settings=Settings(language=language)
    )
