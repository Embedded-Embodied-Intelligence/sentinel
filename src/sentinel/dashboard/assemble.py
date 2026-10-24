"""The cockpit's data from a world and its two runs (WP8; ADR-0021), without language: the
header KPIs of both policies (spec section 7.1), the Gantt rows of baseline plan and realised
execution with their markers, the events of each day, and the decision log of the agent (one row
per deliberation and per approval day, spec sections 4 and 6)."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sentinel.agent.decide import DecisionRecord
from sentinel.dashboard.world import PolicyRun, World
from sentinel.policies.sentinel import SentinelStats
from sentinel.simulation.engine import SimulationResult, Substitution
from sentinel.simulation.events import Absence, NewActivity, WorkIncrease
from sentinel.simulation.state import PAUSED, RUNNING, Observation


@dataclass(frozen=True)
class Kpis:
    """The header numbers of one run: makespan C, on time (C <= D, not truncated), days late,
    cost / B, plan changes (RESEQs and SHIFTs applied) and the planned starts they moved
    (nervousness), temporary workers hired and their cost, crew members substituted, activities
    removed, and Sentinel's deliberations, escalations, deferrals and approvals (None for a
    baseline)."""

    makespan: int
    on_time: bool
    late_days: int
    truncated: bool
    cost_ratio: float
    plan_changes: int
    moved: int
    hired: int
    overtime_cost: float
    substituted: int
    descoped: int
    deliberations: int | None
    escalations: int | None
    deferrals: int | None
    approvals: int | None


def kpis(world: World, policy_run: PolicyRun) -> Kpis:
    result, stats = policy_run.result, policy_run.stats
    sentinel = stats if isinstance(stats, SentinelStats) else None
    on_time = not result.truncated and result.makespan <= world.deadline
    return Kpis(
        makespan=result.makespan,
        on_time=on_time,
        late_days=max(0, result.makespan - world.deadline),
        truncated=result.truncated,
        cost_ratio=result.total_cost / world.budget,
        plan_changes=result.reseqs + result.shifts,
        moved=result.nervousness,
        hired=result.hired,
        overtime_cost=result.overtime_cost,
        substituted=result.n_substituted,
        descoped=len(result.descoped),
        deliberations=None if sentinel is None else sentinel.deliberations,
        escalations=None if sentinel is None else sentinel.escalations,
        deferrals=None if sentinel is None else sentinel.deferrals,
        approvals=None if sentinel is None else sentinel.approvals_applied,
    )


@dataclass(frozen=True)
class Segment:
    """Days `start .. end - 1` on which an activity progressed with `present` crew members,
    `temporary` if a worker hired by OVERTIME was among them."""

    start: int
    end: int
    present: int
    temporary: bool


@dataclass(frozen=True)
class Row:
    """One activity with p_j > 0 in the Gantt chart: nominal duration and crew, baseline start
    (None for a D3 activity), realised start and finish (None if it never started or finished),
    the work segments, the paused days (no present crew member, spec section 3.1 a), its
    substitutions, its D2 shocks (day, factor), the day D3 inserted it and the day DESCOPE
    removed it."""

    activity: int
    duration: int
    demands: tuple[int, ...]
    planned: int | None
    start: int | None
    finish: int | None
    segments: tuple[Segment, ...]
    paused: tuple[tuple[int, int], ...]
    substitutions: tuple[Substitution, ...]
    shocks: tuple[tuple[int, float], ...]
    inserted_day: int | None
    descoped_day: int | None

    @property
    def crew(self) -> int:
        """M_j, the crew size."""
        return sum(self.demands)

    @property
    def inserted(self) -> bool:
        return self.planned is None


def gantt_rows(world: World, result: SimulationResult) -> list[Row]:
    """The rows of every original real activity with p_j > 0, then the D3 activities."""
    instance = world.instance
    n_workers = len(instance.workers)
    inserted = {e.activity: e for e in result.events if isinstance(e, NewActivity)}
    descoped = {d.activity: d.day for d in result.descoped}
    rows = []
    for j in range(len(result.starts)):
        if j < result.n_original:
            act = instance.activities[j]
            if act.duration <= 0:
                continue
            duration, demands, planned = act.duration, act.demands, world.plan.schedule.starts[j]
            inserted_day = None
        elif j in inserted:
            event = inserted[j]
            duration, demands, planned = event.duration, event.demands, None
            inserted_day = event.day
        else:  # pragma: no cover - every activity after the instance's comes from D3
            continue
        segments = tuple(
            Segment(s.start, s.end, len(s.workers), any(w >= n_workers for w in s.workers))
            for s in result.segments
            if s.activity == j
        )
        rows.append(
            Row(
                activity=j,
                duration=duration,
                demands=demands,
                planned=planned,
                start=result.starts[j],
                finish=result.finishes[j],
                segments=segments,
                paused=_paused(result.starts[j], result.finishes[j], segments, result.max_days),
                substitutions=tuple(s for s in result.substitutions if s.activity == j),
                shocks=tuple(
                    (e.day, e.factor)
                    for e in result.events
                    if isinstance(e, WorkIncrease) and e.activity == j
                ),
                inserted_day=inserted_day,
                descoped_day=descoped.get(j),
            )
        )
    return rows


def _paused(
    start: int | None, finish: int | None, segments: Sequence[Segment], max_days: int
) -> tuple[tuple[int, int], ...]:
    """The intervals from the start to the finish (or the day limit) without progress."""
    if start is None:
        return ()
    end = max_days if finish is None else finish
    worked = sorted((s.start, s.end) for s in segments)
    gaps, day = [], start
    for first, last in worked:
        if first > day:
            gaps.append((day, first))
        day = max(day, last)
    if end > day:
        gaps.append((day, end))
    return tuple(gaps)


@dataclass(frozen=True)
class DayEvents:
    """The disruptions of one day: absence onsets of crew members (worker, activity) and of idle
    workers, D2 shocks (activity, factor) and D3 activities (activity, nominal duration)."""

    day: int
    crew_absences: tuple[tuple[int, int], ...] = ()
    idle_absences: tuple[int, ...] = ()
    work_increases: tuple[tuple[int, float], ...] = ()
    new_activities: tuple[tuple[int, int], ...] = ()


def day_events(result: SimulationResult) -> list[DayEvents]:
    """The events of every day that has any, in day order; an absent worker is a crew member if
    it belonged to the crew of an activity running that day (its final crew, or replaced later
    by SUBST)."""
    crew: defaultdict[int, list[tuple[int, int]]] = defaultdict(list)
    idle: defaultdict[int, list[int]] = defaultdict(list)
    work: defaultdict[int, list[tuple[int, float]]] = defaultdict(list)
    new: defaultdict[int, list[tuple[int, int]]] = defaultdict(list)
    for event in result.events:
        if isinstance(event, Absence):
            activity = _crew_activity(result, event.worker, event.day)
            if activity is None:
                idle[event.day].append(event.worker)
            else:
                crew[event.day].append((event.worker, activity))
        elif isinstance(event, WorkIncrease):
            work[event.day].append((event.activity, event.factor))
        elif isinstance(event, NewActivity):
            new[event.day].append((event.activity, event.duration))
    return [
        DayEvents(day, tuple(crew[day]), tuple(idle[day]), tuple(work[day]), tuple(new[day]))
        for day in sorted({*crew, *idle, *work, *new})
    ]


def _crew_activity(result: SimulationResult, worker: int, day: int) -> int | None:
    """The activity whose crew `worker` was in on `day`, if one was running then."""
    for j, start in enumerate(result.starts):
        finish = result.finishes[j]
        if start is None or day < start or (finish is not None and day >= finish):
            continue
        replaced = [s.day for s in result.substitutions if s.activity == j and worker in s.replaced]
        joined = [s.day for s in result.substitutions if s.activity == j and worker in s.workers]
        if worker in result.crews[j] and (not joined or day >= joined[0]):
            return j
        if replaced and day < replaced[0]:
            return j
    return None


TriggerKind = Literal[
    "absence", "idle_absences", "return", "work_increase", "new_activity", "review", "approval"
]


@dataclass(frozen=True)
class Trigger:
    """An event that made the day a decision epoch (spec section 3.1 g): an absence onset or a
    return of a crew member (`activity` its crew), the number of idle workers' onsets, a D2 shock
    of the previous day, a D3 activity, the periodic review or an approval day."""

    kind: TriggerKind
    worker: int | None = None
    activity: int | None = None
    factor: float | None = None
    count: int = 1


@dataclass(frozen=True)
class LogRow:
    """One row of the decision log: a deliberation or an approval day, its triggers and the
    agent's record."""

    day: int
    triggers: tuple[Trigger, ...]
    record: DecisionRecord

    @property
    def approval(self) -> bool:
        return self.record.reason == "approved"

    @property
    def gate(self) -> str:
        """auto, deferred, escalated, approved, or none (NOOP)."""
        if self.approval:
            return "approved"
        return self.record.gate or "none"


def decision_log(world: World, policy_run: PolicyRun) -> list[LogRow]:
    """The deliberations and approval days of a Sentinel run, with their triggers."""
    result, period = policy_run.result, world.config.review_period
    rows = []
    for record in policy_run.records:
        if not record.deliberated and record.reason != "approved":
            continue
        observation = policy_run.observations[record.day]
        triggers = _triggers(result, observation, record.day)
        if record.day % period == 0:
            triggers.append(Trigger("review"))
        if record.reason == "approved" or record.discarded is not None:
            triggers.append(Trigger("approval"))
        rows.append(LogRow(record.day, tuple(triggers), record))
    return rows


def _triggers(result: SimulationResult, observation: Observation, day: int) -> list[Trigger]:
    """The day's events as the agent saw them: crew absences and returns with the activity
    whose crew they are in, idle workers' onsets counted, D2 of the previous day, D3."""
    crews = {
        w: j
        for j, status in enumerate(observation.status)
        if status in (RUNNING, PAUSED)
        for w in observation.assigned[j]
    }
    found: list[Trigger] = []
    idle = 0
    for event in result.events:
        if isinstance(event, Absence):
            moments: tuple[tuple[TriggerKind, int], ...] = (
                ("absence", event.day),
                ("return", event.day + event.length),
            )
            for kind, when in moments:
                if when != day:
                    continue
                if event.worker in crews:
                    found.append(Trigger(kind, event.worker, crews[event.worker]))
                elif kind == "absence":
                    idle += 1
        elif isinstance(event, WorkIncrease) and event.day + 1 == day:
            found.append(Trigger("work_increase", activity=event.activity, factor=event.factor))
        elif isinstance(event, NewActivity) and event.day == day:
            found.append(Trigger("new_activity", activity=event.activity))
    order = ("absence", "return", "work_increase", "new_activity")
    found.sort(key=lambda t: (order.index(t.kind), t.activity or 0, t.worker or 0))
    if idle:
        found.append(Trigger("idle_absences", count=idle))
    return found
