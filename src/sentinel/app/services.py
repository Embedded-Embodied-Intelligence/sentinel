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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.app import decisions, finance, io, planning, reports, simulator
from sentinel.app.config import AppConfig
from sentinel.app.errors import AppError
from sentinel.app.events import (
    OPEN,
    Assessment,
    BaselineSet,
    CheckinDone,
    Corrected,
    Created,
    Decided,
    DefinitionChanged,
    Expired,
    Explained,
    LiveState,
    Recommended,
    RejectReason,
    Source,
    Undone,
    Validity,
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
    role_key,
    validate_definition,
)
from sentinel.app.llm import (
    MAX_NAME_WORDS,
    ClientFactory,
    LlmService,
    TranscriberFactory,
    make_client,
    make_transcriber,
)
from sentinel.app.message_reader import split_clauses
from sentinel.app.messages import render
from sentinel.app.models import CheckIn, Language, Person, ProjectDefinition, Settings, Task
from sentinel.app.store import (
    LOCAL_SESSION,
    EventRow,
    JobRow,
    ProjectRow,
    RecordRow,
    SessionRow,
    Store,
    new_id,
    now,
)
from sentinel.app.views import (
    CausesView,
    CauseView,
    ForecastSummary,
    ForecastView,
    IssueView,
    ProjectSummary,
    ProjectView,
    forecast_view,
    issue_views,
    person_names,
    project_view,
    recommendation_view,
)
from sentinel.experiments.runs import derive_seed
from sentinel.interpret.facts import Names
from sentinel.interpret.redaction import Audience
from sentinel.llm.whisper import Transcript
from sentinel.policies.sentinel import Proposer
from sentinel.simulation.state import Observation
from sentinel.wbs.extract import Extraction

SIMULATIONS_KEPT = 8  # simulator projects kept in memory; others are re-simulated
T = TypeVar("T")
FORECASTS_KEPT = 128  # forecasts, threat lists, causes and validities kept, by the log's contents
CLAUSES_KEPT = 64  # messages whose clauses a review may still show, kept in memory only
VALIDITY_JOB = "validity"  # the validity of a pending decision (11.8), outside the job limit
THREATS_JOB = "threats"  # the job of a threat list: the pages' own, outside the demo's job limit
MIN_ROLE_STEM = 5  # letters two role names must share to count as one role (`team_role`)


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


@dataclass(frozen=True)
class ChanceStep:
    """A check-in's effect on the chance of meeting the deadline (its event, its date)."""

    seq: int
    date: date
    before: float | None
    after: float


class Services:
    """The services of one server."""

    def __init__(
        self,
        config: AppConfig,
        *,
        llm_factory: ClientFactory | None = None,
        transcriber: TranscriberFactory | None = None,
    ) -> None:
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
            session_cap=config.limits.llm_calls_per_session,
            voice_cap=config.limits.voice_seconds_per_day,
            voice_session_cap=config.limits.voice_seconds_per_session,
            factory=llm_factory or partial(make_client, timeout_s=config.llm_timeout_s),
            transcriber=transcriber or make_transcriber,
        )
        self._guard = threading.Lock()
        self._cancelled: set[str] = set()  # simulator jobs to stop after their current day
        self._locks: dict[str, threading.RLock] = {}
        self._live: OrderedDict[str, tuple[int, LiveState]] = OrderedDict()
        self._sims: OrderedDict[str, tuple[int, simulator.Simulation]] = OrderedDict()
        self._forecasts: OrderedDict[str, planning.ForecastResult] = OrderedDict()
        self._drafts: OrderedDict[tuple[str, int, str], ForecastView] = OrderedDict()
        self._threats: OrderedDict[str, planning.ThreatList] = OrderedDict()
        self._causes: OrderedDict[str, planning.Causes | None] = OrderedDict()
        self._validities: OrderedDict[str, decisions.ValidityResult] = OrderedDict()
        self._flights: dict[tuple[str, str], threading.Lock] = {}
        self._clauses: OrderedDict[str, tuple[str, ...]] = OrderedDict()
        self.drafts = reports.Drafts()  # Raporty's drafts, in memory until saved (WP20)
        self._summaries: OrderedDict[str, tuple[str, str]] = OrderedDict()  # Finanse (WP20)
        # set by the web layer (demo): seeds a sandbox with the showcase in a language
        self.showcase: Callable[[str, Language], None] | None = None

    def close(self) -> None:
        self.jobs.shutdown()

    # ---- sessions

    def local_session(self) -> SessionRow:
        return self.store.ensure_session(LOCAL_SESSION, demo=False)

    def new_session(self, language: Language = "pl") -> SessionRow:
        """A new demo sandbox, with the showcase project in `language` if configured."""
        session = self.store.create_session(demo=True)
        if self.showcase is not None:
            self.showcase(session.id, language)
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
        active = self.store.active_jobs(session, besides=THREATS_JOB)
        if self.config.demo and limit is not None and active >= limit:
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
            return self.simulator(session, project_id, language)
        _, state = self._state(session, project_id)
        return project_view(row.id, state, language, row.name)

    def state(self, session: str, project_id: str) -> LiveState:
        """A live project's state (a copy) for the pages."""
        return self._state(session, project_id)[1]

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
            threats = self._threat_list(project_id, current) if result.late else None
            return forecast_view(current.project, result, threats).model_dump(mode="json")

        return self._submit(session, project_id, "forecast", work, language)

    def threats_job(self, session: str, project_id: str, language: Language) -> JobView:
        """The background job of the project's threat list (spec section 11.4): the one queued or
        running, else a new one on the state it finds when it starts. It needs no lock and shows
        nothing but the list, so it does not count towards the demo's limit on a session's jobs."""
        for job in self.store.project_jobs(session, project_id):
            if job.kind == THREATS_JOB:
                return job_view(job, language)

        def work(progress: Progress) -> Mapping[str, Any]:
            _, current = self._state(session, project_id)
            if not _forecastable(current.project):
                return {}
            progress(0.05, "simulating")
            self._cause_list(project_id, self.store.events(session, project_id))
            if not self._forecast(project_id, current).late:
                return {}
            return self._threat_list(project_id, current).model_dump(mode="json")

        return job_view(self.jobs.submit(session, project_id, THREATS_JOB, work), language)

    def checkin(
        self,
        session: str,
        project_id: str,
        checkin: CheckIn,
        language: Language,
        *,
        autonomy: int | None = None,
    ) -> CheckinResult:
        """Apply a check-in (spec section 11.3); a recommendation job follows (11.5), at the
        project's autonomy or at `autonomy` (the v2 interface: 0, spec section 11.8)."""
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
        if not self.jobs.inline:  # inline, a page that needs the list calculates it
            self.threats_job(session, project_id, language)  # ahead of the longer recommendation
        job = None
        _, state = self._state(session, project_id)
        if state.project.definition.deadline is not None and not state.project.finished:
            try:
                job = self.recommend(session, project_id, language, autonomy=autonomy)
            except AppError:
                job = None  # e.g. the job limit; the manager can ask again
        return CheckinResult(
            project=self.live(session, project_id, language), recommendation_job=job
        )

    def recommend(
        self, session: str, project_id: str, language: Language, *, autonomy: int | None = None
    ) -> JobView:
        """A Sentinel deliberation on the latest observation in a job (spec section 11.5), at
        the project's autonomy or at `autonomy` (spec section 11.8)."""
        _, state = self._state(session, project_id)
        _ready(state.project)

        def work(progress: Progress) -> Mapping[str, Any]:
            with self._lock(project_id):
                row, current = self._state(session, project_id)
                project = current.project
                _ready(project)
                progress(0.05, "deliberating")
                recommendation = planning.recommend(
                    project, proposer=self._proposer(project), autonomy=autonomy
                )
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
            if autonomy is not None and applied is None and recommendation.acts:
                with suppress(AppError):  # the v2 interface: its validity follows (11.8)
                    self.validity_job(session, project_id, language)
            return {"recommendation": seq}

        return self._submit(session, project_id, "recommend", work, language)

    # ---- the v2 decision model (spec section 11.8)

    def validity_job(self, session: str, project_id: str, language: Language) -> JobView:
        """The validity date and cost of delay of the pending recommendation in a background
        job, stored as a `validity` event; outside the demo's job limit, like the threats. The
        job of a pending one already running is returned."""
        for job in self.store.project_jobs(session, project_id):
            if job.kind == VALIDITY_JOB and job.status in ("queued", "running"):
                return job_view(job, language)

        def work(progress: Progress) -> Mapping[str, Any]:
            _, current = self._state(session, project_id)
            entry = current.open
            if entry is None or entry.validity is not None:
                return {}
            progress(0.05, "simulating")
            label = entry.recommendation.record.chosen
            key = f"{current.fingerprint}|{label}"  # the same log, the same answer (WP17)
            recommendation = entry.recommendation
            try:
                found = self._once(
                    "validity",
                    self._validities,
                    key,
                    lambda: decisions.validity(current.project, recommendation),
                )
            except ValueError:
                return {}  # no longer the recommendation of the current observation
            with self._lock(project_id):
                row, latest = self._state(session, project_id)
                again = latest.recommendation(entry.seq)
                if (
                    again is None
                    or again.status not in OPEN
                    or again.recommendation.record.chosen != label
                ):
                    return {}
                event = Validity(
                    recommendation=entry.seq,
                    label=label,
                    chances=found.chances,
                    noop=found.noop,
                    valid_day=found.valid_day,
                    delay=found.delay,
                )
                return {"validity": self._append(session, row, "validity", event)}

        return job_view(self.jobs.submit(session, project_id, VALIDITY_JOB, work), language)

    def correction_options(self, session: str, project_id: str, seq: int) -> list[decisions.Option]:
        """The corrections of a pending recommendation the engine accepts (11.8)."""
        _, state = self._state(session, project_id)
        entry = state.recommendation(seq)
        if entry is None or entry.status not in OPEN:
            return []
        return decisions.options(state.project, entry.recommendation)

    def correct(
        self, session: str, project_id: str, seq: int, key: str, language: Language
    ) -> ProjectView:
        """The manager's correction of a pending recommendation (spec section 11.8): the
        corrected action evaluated and stored as its choice; its validity follows."""
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            entry = state.recommendation(seq)
            if entry is None:
                raise AppError("recommendation_not_found", "not_found")
            if entry.status not in OPEN or entry.seq != state.open_seq():
                status = render(f"status_{entry.status}", language)
                raise AppError("recommendation_closed", "conflict", status=status)
            try:
                replacement = decisions.correct(state.project, entry.recommendation, key)
            except ValueError as exc:
                raise AppError("field_invalid", field="option", detail=key) from exc
            self._append(
                session,
                row,
                "correction",
                Corrected(recommendation=seq, replacement=replacement, option=key),
            )
        with suppress(AppError):
            self.validity_job(session, project_id, language)
        return self.live(session, project_id, language)

    def distribution(
        self, session: str, project_id: str, seq: int
    ) -> tuple[list[int], list[int]] | None:
        """The makespans with and without a pending recommendation's action (11.8 details)."""
        _, state = self._state(session, project_id)
        entry = state.recommendation(seq)
        if entry is None or entry.status not in OPEN:
            return None
        try:
            return decisions.distribution(state.project, entry.recommendation)
        except ValueError:
            return None

    def dry_run(
        self, session: str, project_id: str, checkin: CheckIn
    ) -> tuple[ForecastView, ForecastView]:
        """The forecast now and with a draft check-in applied (v2 "Wpływ na projekt", 11.8):
        nothing is stored; the draft's forecasts are kept by the draft and the project's state."""
        _, state = self._state(session, project_id)
        project = state.project
        _ready(project, need_deadline=False)
        before = forecast_view(project, self._forecast(project_id, state))
        key = (project_id, state.last_change, checkin.model_dump_json())
        with self._guard:
            found = self._drafts.get(key)
        if found is None:
            trial = project.copy()
            try:
                trial.apply_checkin(trial.resolve_checkin(checkin))
            except LiveError as exc:
                raise AppError.of(exc) from exc
            found = forecast_view(trial, planning.forecast(trial))
            with self._guard:
                self._drafts[key] = found
                while len(self._drafts) > FORECASTS_KEPT:
                    self._drafts.popitem(last=False)
        return before, found

    def expire(self, session: str, project_id: str, today: date) -> None:
        """An `expiry` event for the pending recommendation whose validity date is before
        `today` (spec section 11.8); nothing is ever applied by it."""
        _, state = self._state(session, project_id)
        entry = state.open
        if entry is None or entry.validity is None or entry.validity.valid_day is None:
            return
        if state.project.calendar.date_of(entry.validity.valid_day) >= today:
            return
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            again = state.recommendation(entry.seq)
            if again is not None and again.status in OPEN:
                self._append(session, row, "expiry", Expired(recommendation=entry.seq))

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
        self,
        session: str,
        project_id: str,
        seq: int,
        verdict: Verdict,
        language: Language,
        *,
        reason: RejectReason | None = None,
        note: str | None = None,
        autonomy: int | None = None,
        assessment: Assessment | None = None,
    ) -> ProjectView:
        """The manager's decision on a recommendation (spec section 11.5); a rejection with its
        reason and words (v2), a fresh recommendation at `autonomy` after a discarded one, and
        the manager's own choice made first ("Twoja ocena", section 11.8)."""
        follow = False
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            entry = state.recommendation(seq)
            if entry is None:
                raise AppError("recommendation_not_found", "not_found")
            if entry.status not in OPEN:
                status = render(f"status_{entry.status}", language)
                raise AppError("recommendation_closed", "conflict", status=status)
            project = state.project
            valid = entry.validity
            brief = decisions.brief_of(
                entry.recommendation,
                None if valid is None else valid.valid_day,
                None if valid is None else valid.delay,
            )
            event = Decided(
                recommendation=seq,
                verdict=verdict,
                reason=reason if verdict == "reject" else None,
                note=(note or "").strip()[:300] or None if verdict == "reject" else None,
                brief=brief,
                assessment=assessment if verdict in ("approve", "reject") else None,
            )
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
                    event = event.model_copy(update={"discarded": outcome})
                    follow = True
                else:
                    event = event.model_copy(update={"applied": outcome})
            self._append(session, row, "decision", event)
        if follow:
            with suppress(AppError):  # e.g. the job limit; the manager can ask again
                self.recommend(session, project_id, language, autonomy=autonomy)
        return self.live(session, project_id, language)

    def undo(self, session: str, project_id: str, seq: int, language: Language) -> ProjectView:
        """Undo an automatic plan change (spec section 11.5): the planned starts it changed get
        their values before it back."""
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            entry = state.recommendation(seq)
            if entry is None:
                raise AppError("recommendation_not_found", "not_found")
            if not state.can_undo(entry) or entry.applied is None:
                raise AppError("undo_impossible", "conflict")
            rows = [e for e in self.store.events(session, project_id) if e.seq < seq]
            before = replay(rows).project
            plan = {key: before.tasks[key].planned for key in entry.applied.plan}
            event = Undone(recommendation=seq, plan=plan, sink_plan=before.sink_plan)
            self._append(session, row, "undo", event)
        return self.live(session, project_id, language)

    def forecast_now(self, session: str, project_id: str) -> ForecastView | None:
        """The forecast of the project now with its threat list if that is known (spec section
        11.4), None for a project without a valid plan or a finished one."""
        _, state = self._state(session, project_id)
        if not _forecastable(state.project):
            return None
        view = forecast_view(
            state.project, self._forecast(project_id, state), self._known_threats(project_id, state)
        )
        return self._with_causes(view, project_id, state, self.store.events(session, project_id))

    def forecast_summary(
        self, session: str, project_id: str, language: Language, *, with_threats: bool = False
    ) -> ForecastSummary | None:
        """The forecast of the project now (spec section 11.4) and the chance of meeting the
        deadline before its latest check-in (the trend), None for a project without a valid
        plan or a finished one. Computed in the request (0.2-0.5 s) and cached by the project's
        last change, since a forecast is deterministic for its state. The threat list comes from
        its job (`threats_job`), or with `with_threats` from here, for a page that cannot wait."""
        _, state = self._state(session, project_id)
        if not _forecastable(state.project):
            return None
        result = self._forecast(project_id, state)
        threats = self._known_threats(project_id, state)
        if with_threats and result.late and threats is None:
            threats = self._threat_list(project_id, state)
        rows = self.store.events(session, project_id)
        current = self._with_causes(
            forecast_view(state.project, result, threats), project_id, state, rows
        )
        previous = None
        checkins = [row.seq for row in rows if row.type == "checkin"]
        if checkins and current.p_on_time is not None:
            before = replay([row for row in rows if row.seq < checkins[-1]])
            if _forecastable(before.project) and before.project.definition.deadline is not None:
                previous = self._forecast(project_id, before).p_on_time
        note = promise_note(rows, state, result)
        return ForecastSummary(forecast=current, previous_p=previous, promise_note=note)

    def chance_history(
        self, session: str, project_id: str
    ) -> tuple[list[ChanceStep], float | None]:
        """The chance of meeting the deadline before and after every check-in (spec section 11.4,
        on the states of the log) and now; every forecast is deterministic and cached."""
        rows = self.store.events(session, project_id)
        steps = []
        for row in rows:
            if row.type != "checkin":
                continue
            before = replay([r for r in rows if r.seq < row.seq])
            after = replay([r for r in rows if r.seq <= row.seq])
            p_after = self._deadline_chance(project_id, after)
            if p_after is None:
                continue
            steps.append(
                ChanceStep(
                    seq=row.seq,
                    date=after.project.checkins[-1][0],
                    before=self._deadline_chance(project_id, before),
                    after=p_after,
                )
            )
        return steps, self._deadline_chance(project_id, replay(rows))

    def forecast_of(self, project_id: str, state: LiveState) -> planning.ForecastResult | None:
        """The forecast of a state of the project's log (cached), None without a valid plan or
        for a finished project (the v2 charts, WP15)."""
        if not _forecastable(state.project):
            return None
        return self._forecast(project_id, state)

    def chance_of(self, project_id: str, state: LiveState) -> float | None:
        """The chance of meeting the deadline of a state of the project's log (cached), None
        without a plan or a deadline (the v2 banner and charts, WP15)."""
        return self._deadline_chance(project_id, state)

    def _deadline_chance(self, project_id: str, state: LiveState) -> float | None:
        if not _forecastable(state.project) or state.project.definition.deadline is None:
            return None
        return self._forecast(project_id, state).p_on_time

    def known_chance(self, project_id: str, state: LiveState) -> float | None:
        """The chance of meeting the deadline if the forecast of `state` is cached, else None:
        what a page can show without calculating anything."""
        with self._guard:
            found = self._forecasts.get(forecast_key(state))
        return None if found is None else found.p_on_time

    def _forecast(self, project_id: str, state: LiveState) -> planning.ForecastResult:
        # The same log, the same forecast, in any sandbox (WP17).
        return self._once(
            "forecast",
            self._forecasts,
            forecast_key(state),
            lambda: planning.forecast(state.project),
        )

    def _once(self, kind: str, cache: OrderedDict[str, T], key: str, compute: Callable[[], T]) -> T:
        """`cache[key]`, computed once even when several requests ask for it at the same time
        (WP17: many demo visitors opening the same showcase); the oldest go beyond
        `FORECASTS_KEPT`."""
        if not key:  # a state without its log's fingerprint is never shared
            return compute()
        with self._guard:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
            flight = self._flights.setdefault((kind, key), threading.Lock())
        with flight:
            with self._guard:
                if key in cache:
                    cache.move_to_end(key)
                    return cache[key]
            result = compute()
            with self._guard:
                cache[key] = result
                while len(cache) > FORECASTS_KEPT:
                    cache.popitem(last=False)
                self._flights.pop((kind, key), None)
            return result

    def _with_causes(
        self, view: ForecastView, project_id: str, state: LiveState, rows: Sequence[EventRow]
    ) -> ForecastView:
        """The forecast with the causes of the move at the latest check-in, if known, or a mark
        that its background job is still calculating them (spec section 11.4, v2.2.0)."""
        checkins = [row for row in rows if row.type == "checkin"]
        if not checkins or view.p_on_time is None:
            return view
        key = forecast_key(replay([row for row in rows if row.seq <= checkins[-1].seq]))
        with self._guard:
            if key not in self._causes:
                return view.model_copy(update={"causes_pending": True})
            found = self._causes[key]
        if found is None or not found.causes:
            return view
        project = state.project
        dates = [day for day, _ in project.checkins]
        since = dates[-2] if len(dates) > 1 else project.calendar.date_of(0)
        causes = CausesView(
            reported=dates[-1],
            since=since,
            p_before=found.p_before,
            p_after=found.p_after,
            lines=[
                CauseView(kind=c.kind, name=c.name, p_without=c.p_without) for c in found.causes
            ],
        )
        return view.model_copy(update={"causes": causes})

    def _cause_list(self, project_id: str, rows: Sequence[EventRow]) -> planning.Causes | None:
        """The causes of the move of the chance at the latest check-in (spec section 11.4,
        v2.2.0), deterministic for the log up to it and kept; None without a check-in or a
        chance before and after it."""
        checkins = [row for row in rows if row.type == "checkin"]
        if not checkins:
            return None
        seq = checkins[-1].seq
        before = replay([row for row in rows if row.seq < seq])
        after = replay([row for row in rows if row.seq <= seq])

        def compute() -> planning.Causes | None:
            if not (_forecastable(before.project) and _forecastable(after.project)):
                return None
            p_before = self._forecast(project_id, before).p_on_time
            p_after = self._forecast(project_id, after).p_on_time
            if p_before is None or p_after is None:
                return None
            checkin = CheckinDone.model_validate(checkins[-1].payload).checkin
            return planning.causes(before.project, checkin, p_before, p_after)

        return self._once("causes", self._causes, forecast_key(after), compute)

    def _known_threats(self, project_id: str, state: LiveState) -> planning.ThreatList | None:
        with self._guard:
            return self._threats.get(threat_key(state))

    def _threat_list(self, project_id: str, state: LiveState) -> planning.ThreatList:
        """The threat list of `state`, deterministic for it and kept while nothing changes that
        a forecast reads: long enough to matter, it outlives a recommendation or a refusal."""
        return self._once(
            "threats",
            self._threats,
            threat_key(state),
            lambda: planning.threats(state.project, rollouts=planning.THREAT_ROLLOUTS),
        )

    def read_message(
        self, session: str, project_id: str, text: str, when: date, language: Language
    ) -> JobView:
        """The events of a check-in message read by the LLM (spec section 10.2) in a job, as
        reports for the manager to confirm; nothing is saved."""
        if not text.strip():
            raise AppError("message_empty")
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")
        _, state = self._state(session, project_id)
        _ready(state.project, need_deadline=False)
        seed = derive_seed(state.project.definition.settings.seed, "llm", "message", text)

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.05, "reading")
            _, current = self._state(session, project_id)
            draft = self.llm.read_message(current.project, text, when, seed, session)
            return draft.model_dump(mode="json")

        job = self._submit(session, project_id, "message", work, language)
        # The clauses the review names by number stay in memory only: the job's result, kept in
        # the database, holds no text of the message (invariant 7; WP12, nothing dropped silently).
        language_of = state.project.definition.settings.language
        with self._guard:
            self._clauses[job.id] = split_clauses(text, language_of)
            while len(self._clauses) > CLAUSES_KEPT:
                self._clauses.popitem(last=False)
        return job

    def message_clauses(self, job_id: str) -> tuple[str, ...]:
        """The clauses of the message a reading job read, while this process keeps them."""
        with self._guard:
            return self._clauses.get(job_id, ())

    # ---- Raporty (v3 spec section 7; spec section 11.9)

    def report_names(self, session: str) -> Names:
        """The people, tasks and project names of the session's live projects (the fact
        guard's names)."""
        people: list[str] = []
        tasks: list[str] = []
        projects: list[str] = []
        for summary in self.projects(session):
            if summary.kind != "live":
                continue
            definition = self.state(session, summary.id).project.definition
            projects.append(definition.name or summary.name)
            people += [p.name for p in definition.team]
            tasks += [t.name for t in definition.tasks]
        return reports.session_names(people, tasks, projects)

    def new_draft(
        self,
        session: str,
        title: str,
        text: str,
        audiences: Sequence[str],
        day: date,
        language: Language,
    ) -> tuple[reports.Draft, JobView]:
        """A new report's draft and the job that edits it for each audience (nothing stored)."""
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")
        try:
            title, text, chosen = reports.validate(title, text, audiences)
        except ValueError as exc:
            raise AppError(f"report_{exc}") from exc
        draft = reports.Draft(
            id=new_id(),
            session=session,
            title=title,
            day=day,
            original=text,
            audiences=chosen,
            language=language,
            names=self.report_names(session),
        )
        self.drafts.put(draft)
        return draft, self._edit_job(draft, chosen, language)

    def _edit_job(
        self, draft: reports.Draft, audiences: Sequence[Audience], language: Language
    ) -> JobView:
        guard_language = reports.text_language(draft.original, language)

        def work(progress: Progress) -> Mapping[str, Any]:
            for index, audience in enumerate(audiences):
                progress(index / len(audiences), audience)
                seed = derive_seed(0, "llm", "redact", audience, draft.original)
                try:
                    text, model = self.llm.redact(
                        draft.original, audience, guard_language, seed, draft.session
                    )
                    draft.versions[audience] = reports.Version(audience, text, model=model)
                except AppError as exc:
                    draft.versions[audience] = reports.Version(audience, error=exc.code)
            return {"draft": draft.id}  # no text of the report in the database

        return self._submit(draft.session, None, "redact", work, language)

    def draft(self, session: str, draft_id: str) -> reports.Draft:
        found = self.drafts.get(session, draft_id)
        if found is None:
            raise AppError("draft_not_found", "not_found")
        return found

    def save_draft(self, session: str, draft_id: str) -> str:
        """Store the draft as the session's report (a new one, or a new version of the one it
        came from); returns the report's id."""
        draft = self.draft(session, draft_id)
        if draft.report_id is None:
            draft.report_id = new_id()
        self.store.save_report(session, draft.report_id, draft.title, reports.payload(draft))
        return draft.report_id

    def saved_reports(self, session: str) -> list[RecordRow]:
        return self.store.reports(session)

    def saved_report(self, session: str, report_id: str) -> RecordRow:
        found = self.store.report(session, report_id)
        if found is None:
            raise AppError("report_not_found", "not_found")
        return found

    def reopen(self, session: str, report_id: str) -> reports.Draft:
        """A saved report as a draft again, to change its decisions and save it anew."""
        row = self.saved_report(session, report_id)
        draft = reports.from_payload(
            new_id(), session, row.id, row.title, row.payload, self.report_names(session)
        )
        self.drafts.put(draft)
        return draft

    def delete_report(self, session: str, report_id: str) -> None:
        if not self.store.delete_report(session, report_id):
            raise AppError("report_not_found", "not_found")

    # ---- Finanse (v3 spec section 8; spec section 11.9)

    def portfolio(self, session: str, language: Language) -> list[finance.Line]:
        """Every live project with a plan and a budget: budget, cost so far, the forecast's
        mean cost at the end and its chance within the budget (a finished project's cost is
        final)."""
        lines = []
        for summary in self.projects(session):
            if summary.kind != "live":
                continue
            view = self.live(session, summary.id, language)
            if not view.has_plan or view.budget is None:
                continue
            spent = view.cost_so_far or 0.0
            result = self.forecast_of(summary.id, self.state(session, summary.id))
            forecast = spent if result is None else result.mean_cost
            chance = None if result is None else result.p_within_budget
            lines.append(
                finance.Line(
                    summary.id, view.name, view.budget, spent, forecast, chance, view.person_days
                )
            )
        return lines

    def board_summary(self, session: str, sheet: str, language: Language) -> JobView:
        """Role 4 with the audience "summary" on a fact sheet that code wrote (the page's
        portfolio); the summary is kept in memory only, never stored."""
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")
        key = new_id()

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.1, "summary")
            seed = derive_seed(0, "llm", "redact", "summary", sheet)
            text, model = self.llm.redact(sheet, "summary", language, seed, session)
            with self._guard:
                self._summaries[key] = (text, model)
                while len(self._summaries) > reports.MAX_DRAFTS:
                    self._summaries.popitem(last=False)
            return {"summary": key}

        return self._submit(session, None, "summary", work, language)

    def summary_of(self, key: str) -> tuple[str, str] | None:
        with self._guard:
            return self._summaries.get(key)

    def budget_requests(self, session: str) -> list[finance.Request]:
        return [
            finance.Request.model_validate(r.payload) for r in self.store.budget_requests(session)
        ]

    def file_request(
        self,
        session: str,
        source: str,
        target: str,
        amount: float,
        reason: str,
        language: Language,
    ) -> finance.Request:
        """A pending budget request between two projects of the portfolio."""
        lines = {line.id: line for line in self.portfolio(session, language)}
        if source not in lines or target not in lines:
            raise AppError("budget_unknown")
        try:
            request = finance.new_request(new_id(), lines[source], lines[target], amount, reason)
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        self.store.save_budget_request(session, request.id, finance.as_payload(request))
        return request

    def decide_request(
        self, session: str, request_id: str, approve: bool, language: Language
    ) -> finance.Request:
        """A person's decision on a pending request: rejected; or approved and applied as two
        budget changes; or approved and not applied, with the reason (spec section 11.9)."""
        row = self.store.budget_request(session, request_id)
        if row is None:
            raise AppError("request_not_found", "not_found")
        request = finance.Request.model_validate(row.payload)
        if request.status != "pending":
            raise AppError("budget_decided", "conflict")
        if not approve:
            done = finance.decided(request, "rejected")
        else:
            lines = {line.id: line for line in self.portfolio(session, language)}
            kinds = {p.id: p.kind for p in self.projects(session)}
            why = finance.applicable(request, lines, kinds)
            if why is not None:
                spent = lines[request.source].spent if why == "below_spent" else None
                done = finance.decided(request, "not_applied", why, spent)
            else:
                move = finance.BudgetMove(
                    request=request.id,
                    source=lines[request.source].name,
                    target=lines[request.target].name,
                    amount=request.amount,
                    reason=request.reason,
                )
                self._move_budget(session, request.source, -request.amount, move)
                self._move_budget(session, request.target, request.amount, move)
                done = finance.decided(request, "approved")
        self.store.save_budget_request(session, done.id, finance.as_payload(done))
        return done

    def _move_budget(
        self, session: str, project_id: str, change: float, move: finance.BudgetMove
    ) -> None:
        """One project's budget changed by `change` as a definition change that carries the
        request (a default budget becomes explicit)."""
        with self._lock(project_id):
            row, state = self._state(session, project_id)
            project = state.project
            budget = project.require_model().budget
            assert budget is not None
            definition = project.definition.model_copy(update={"budget": budget + change})
            try:
                project.set_definition(definition)
            except LiveError as exc:
                raise AppError.of(exc) from exc
            event = DefinitionChanged(definition=definition, request=move)
            self._append(session, row, "definition", event, name=definition.name or row.name)

    def transcribe(
        self,
        session: str,
        project_id: str | None,
        audio: bytes,
        content_type: str,
        language: Language,
        *,
        preview: bool = False,
    ) -> Transcript:
        """A recording of a project's message box written out (WP14, ADR-0031), in the page's
        language, with the names of the team and the tasks as Whisper's vocabulary (none without
        a project: the v2 wizard); `preview` for the live preview of a recording still running
        (v2, WP15). The text goes back to the page only: neither it nor the audio is stored."""
        vocabulary = ""
        if project_id is not None:
            row = self._row(session, project_id)
            if row.kind != "live":
                raise AppError("not_a_live_project", "invalid")
            definition = self._state(session, project_id)[1].project.definition
            names = [p.name for p in definition.team] + [t.name for t in definition.tasks]
            vocabulary = ", ".join(dict.fromkeys(n for n in names if n))
        found = self.llm.transcribe(
            audio,
            content_type,
            language=language,
            vocabulary=vocabulary,
            preview=preview,
            session=session,
        )
        if not found.text:
            raise AppError("voice_nothing", "invalid")
        return found

    def test_voice(self, session: str, language: Language) -> JobView:
        """A connection test of recordings in a job."""
        if not self.llm.voice:
            raise AppError("voice_disabled", "unavailable")

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.1, "testing")
            return {"model": self.llm.test_voice()}

        return self._submit(session, None, "voice_test", work, language)

    def test_llm(self, session: str, language: Language) -> JobView:
        """A connection test of the configured language model in a job."""
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.1, "testing")
            return {"model": self.llm.test()}

        return self._submit(session, None, "llm_test", work, language)

    def explain(self, session: str, project_id: str, seq: int, language: Language) -> JobView:
        """An LLM explanation of a recommendation with its faithfulness badge (spec 10.4)."""
        _, state = self._state(session, project_id)
        entry = state.recommendation(seq)
        if entry is None:
            raise AppError("recommendation_not_found", "not_found")
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")

        def work(progress: Progress) -> Mapping[str, Any]:
            _, current = self._state(session, project_id)
            found = current.recommendation(seq)
            assert found is not None
            before = [e for e in self.store.events(session, project_id) if e.seq < seq]
            observation = replay(before).project.observation()
            project = current.project
            roles = project.require_model().role_names
            record = found.recommendation.as_shown  # the page's rows and figures (11.5)
            key = derive_seed(project.definition.settings.seed, "llm", "explain", str(seq))
            # Without the project's lock: a model may take minutes, and nothing here changes.
            shown = recommendation_view(project, found, language)
            names = {shown.label: shown.title} | {a.label: a.title for a in shown.alternatives}
            explanation = self.llm.explain(
                record,
                observation,
                planning.sentinel_params(project),
                roles,
                key,
                language=language,
                names=names,
                reason=shown.reason_text,
                session=session,
            )
            with self._lock(project_id):
                self._append(
                    session,
                    self._row(session, project_id),
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

    def plan_csv(self, session: str, project_id: str, language: Language = "en") -> str:
        _, state = self._state(session, project_id)
        project = state.project
        if project.baseline is None:
            raise AppError("no_baseline")
        return io.plan_csv(project, person_names(project), language)

    def extract(
        self, session: str, text: str, language: Language, *, team: Sequence[Person] = ()
    ) -> JobView:
        """Tasks and team read from a description by the LLM (WP6a extraction with repair
        rounds), in the role names of the project's `team` if it has one; the draft is returned
        for review, not saved."""
        if not text.strip():
            raise AppError("text_empty")
        if not self.llm.available:
            raise AppError("llm_disabled", "unavailable")
        seed = derive_seed(2026, "llm", "extract", text)
        roles = role_counts(team)

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.05, "reading")
            found = self.llm.extract(text, seed, roles, session)
            final = found.final
            if final.response.value is None:
                detail = (
                    "no valid answer" if final.response.error is None else final.response.error.kind
                )
                raise AppError("extraction_failed", "invalid", detail=detail)
            draft = draft_definition(final.response.value, now().date(), language, tuple(roles))
            return {
                "definition": draft.model_dump(mode="json"),
                "rounds": len(found.rounds),
                "issues": len(final.issues),
                "roles_outside": roles_outside(draft, tuple(roles)),
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
            return self.simulator(session, row.id, language).model_dump(mode="json")

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

    def simulation_ready(self, session: str, project_id: str) -> bool:
        """Whether a simulator project's runs are in memory, so that reading them is quick."""
        row = self._row(session, project_id)
        with self._guard:
            cached = self._sims.get(project_id)
        return cached is not None and cached[0] == row.seq

    def load_simulation(self, session: str, project_id: str, language: Language) -> JobView:
        """Replay a simulator project's days in a job: after a restart this takes as long as
        simulating them did, and a page must not wait for it (QA-03)."""

        def work(progress: Progress) -> Mapping[str, Any]:
            progress(0.05, "simulating")
            with self._lock(project_id):
                self._simulation(session, project_id)
            return {"project": project_id}

        return self._submit(session, project_id, "simulator", work, language)

    def with_simulation[T](
        self, session: str, project_id: str, read: Callable[[simulator.Simulation], T]
    ) -> T:
        """`read` applied to a simulator project's runs while no job advances them."""
        with self._lock(project_id):
            return read(self._simulation(session, project_id)[1])

    def simulator(
        self, session: str, project_id: str, language: Language = "en"
    ) -> simulator.SimulatorView:
        with self._lock(project_id):
            row, simulation = self._simulation(session, project_id)
            return simulator.simulator_view(row.id, row.seq, simulation, language)

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
                moved = simulation.advance(
                    days,
                    lambda f: progress(f, "simulating"),
                    stop=lambda: progress.job_id in self._cancelled,
                )
                self._cancelled.discard(progress.job_id)
                seq = row.seq
                if moved:
                    seq = self.store.append(
                        session, project_id, "advance", {"days": moved}, expected=row.seq
                    )
                with self._guard:
                    self._sims[project_id] = (seq, simulation)
                view = simulator.simulator_view(project_id, seq, simulation, language)
                return view.model_dump(mode="json")

        return self._submit(session, project_id, "advance", work, language)

    def cancel_advance(self, session: str, job_id: str) -> None:
        """Stop a simulator job after the day it is on; the days done so far count."""
        job = self.job_row(session, job_id)
        if job.kind == "advance" and job.status in ("queued", "running"):
            self._cancelled.add(job_id)

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


def promise_note(
    rows: Sequence[EventRow], state: LiveState, result: planning.ForecastResult
) -> str | None:
    """Why the forecast after an approval differs from what its card promised (spec section
    11.5, v2.2.0; B3 of the WP12 test): None if the latest change of the forecast is not an
    approval or the figures are those shown on the card (chance in whole per cent, the most
    likely and the bad finish, the expected cost in whole per cent of the budget), else what
    changed between the recommendation and the approval."""
    last = next((row for row in rows if row.seq == state.last_forecast_change), None)
    if last is None or last.type != "decision":
        return None
    entry = state.recommendation(Decided.model_validate(last.payload).recommendation)
    comparison = None if entry is None else entry.recommendation.comparison
    if entry is None or entry.status != "approved" or comparison is None:
        return None
    promised = comparison.impacts[0]
    if promised.quantiles is None:  # stored before v2.2.0
        return None
    budget = state.project.require_model().budget or 1.0
    if (
        planning.shown_chance(promised.p_on_time) == planning.shown_chance(result.p_on_time or 0)
        and promised.quantiles[1:] == result.quantiles[1:]
        and planning.half_up(100 * promised.mean_cost / budget)
        == planning.half_up(100 * result.mean_cost / budget)
    ):
        return None
    then = replay([row for row in rows if row.seq <= entry.seq]).project.definition
    now = state.project.definition
    if then.deadline != now.deadline:
        return "deadline"
    if then.budget != now.budget:
        return "budget"
    if then.settings.model_copy(update={"autonomy": 0}) != now.settings.model_copy(
        update={"autonomy": 0}
    ):
        return "settings"
    return "replanned"


def _forecastable(project: LiveProject) -> bool:
    """Whether a forecast can be made: a valid definition with a plan, not yet finished."""
    return (
        project.baseline is not None
        and not project.finished
        and not errors(_validate(project.definition))
    )


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


def forecast_key(state: LiveState) -> str:
    """A forecast's key: the log's contents and the number of futures (WP17)."""
    return f"{state.fingerprint}|{planning.FORECAST_ROLLOUTS}" if state.fingerprint else ""


def threat_key(state: LiveState) -> str:
    """A threat list's key: the log's contents and the rule's settings (WP17)."""
    if not state.forecast_fingerprint:
        return ""
    return f"{state.forecast_fingerprint}|{planning.THREAT_ROLLOUTS}|{planning.THREAT_SENSITIVITY}"


def _copy(state: LiveState) -> LiveState:
    """A copy of a cached state that an operation may change."""
    return LiveState(
        state.project.copy(),
        state.source,
        state.seq,
        [*state.recommendations],
        state.last_change,
        state.last_forecast_change,
        state.fingerprint,
        state.forecast_fingerprint,
    )


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


def role_counts(team: Sequence[Person]) -> dict[str, int]:
    """The roles of a team, each named as it was first written, with their people."""
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for person in team:
        if person.role.strip():
            name = names.setdefault(role_key(person.role), person.role)
            counts[name] = counts.get(name, 0) + 1
    return counts


def team_role(role: str, roles: Sequence[str]) -> str:
    """The team's name of a role an AI wrote: the same role by `role_key`, else the one role
    with the same stem, since a description inflects them ("analityczka", "testerka" for
    "Analityk", "Tester"); else as written, for the manager to decide."""
    key = role_key(role)
    keys = {role_key(known): known for known in roles}
    if key in keys:
        return keys[key]
    same = [known for other, known in keys.items() if _same_stem(key, other)]
    return same[0] if len(same) == 1 else role


def _same_stem(a: str, b: str) -> bool:
    """Whether two role keys differ only in their last letters (at most three of the shorter)."""
    shared = next(
        (i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b))
    )
    return shared >= MIN_ROLE_STEM and shared >= min(len(a), len(b)) - 3


def roles_outside(definition: ProjectDefinition, roles: Sequence[str]) -> list[str]:
    """The roles a draft's crews name that are not among the team's `roles`."""
    if not roles:
        return []
    known = {role_key(role) for role in roles}
    found = {
        role: None
        for task in definition.tasks
        for role, count in task.crew.items()
        if count > 0 and role_key(role) not in known
    }
    return list(found)


def draft_definition(
    extraction: Extraction, start: date, language: Language, roles: Sequence[str] = ()
) -> ProjectDefinition:
    """A definition from an extraction (WP6a) for the manager to review: people named after
    their role ("Tester 1"), tasks T1, T2, ... with predecessors by key and the crews in the
    role names of the project's team (`roles`), if it has one."""
    people: list[Person] = []
    for member in extraction.team:
        for i in range(max(0, member.count)):
            people.append(
                Person(key=f"P{len(people) + 1}", name=f"{member.role} {i + 1}", role=member.role)
            )
    keys = {a.name: f"T{i + 1}" for i, a in enumerate(extraction.activities)}
    tasks = []
    for a in extraction.activities:
        # The application's fields (WP12): a short name, the sentence and the optional flag.
        description = " ".join(str(getattr(a, "description", "") or "").split())
        words = a.name.split()
        name = a.name
        if len(words) > MAX_NAME_WORDS:  # still long after the repair rounds: cut it here
            name = " ".join(words[:MAX_NAME_WORDS])
            description = description or a.name
        tasks.append(
            Task(
                key=keys[a.name],
                name=name[:120],
                duration=a.duration_days,
                crew=_merged_crew(a.crew, roles),
                predecessors=tuple(keys.get(p, p) for p in a.predecessors),
                optional=bool(getattr(a, "optional", False)),
                description=description[:500] if description != name else "",
            )
        )
    return ProjectDefinition(
        name="",
        start=start,
        team=tuple(people),
        tasks=tuple(tasks),
        settings=Settings(language=language),
    )


def _merged_crew(crew: Mapping[str, int], roles: Sequence[str]) -> dict[str, int]:
    """A crew in the team's role names; two names of one role add up."""
    merged: dict[str, int] = {}
    for role, count in crew.items():
        name = team_role(role, roles)
        merged[name] = merged.get(name, 0) + count
    return merged
