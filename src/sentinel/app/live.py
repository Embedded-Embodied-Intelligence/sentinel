"""A live project and its mapping onto the model (spec section 11).

`validate_definition` checks a project as the manager defined it and explains every issue in
plain language (`Issue`, rendered by `messages`). `build_model` maps a valid definition onto a
`ProjectInstance` (roles in the order of their first person, people as workers in the order
listed, tasks as activities 1..n between the dummy source and sink), its costs, deadline D and
budget B. `LiveProject` holds the tracking state that the event log rebuilds: the baseline plan,
the tasks' starts, finishes, work done and crews, the absences, the reported work increases, the
tasks added at check-ins, the temporary workers and SUBST handovers of approved actions.
`observation()` is the `Observation` of the current day (spec section 3), `resolve_checkin` turns
a check-in into its effects or the issues that stop it (spec section 11.3), and `resolve_action`
applies a decision through the engine's own `rehearse` and maps the state it leaves back onto
the project (spec section 11.5). Days are model days; `calendar` shows them as dates.
"""

import copy
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sentinel.app.calendar import WorkCalendar
from sentinel.app.models import (
    BUDGET_RESERVE,
    CheckIn,
    NewTaskReport,
    ProjectDefinition,
    TaskReport,
)
from sentinel.model.instance import Activity, ProjectInstance, Role, Worker
from sentinel.policies.base import Decision
from sentinel.scheduling.bounds import critical_path_lower_bound
from sentinel.simulation.engine import rehearse
from sentinel.simulation.state import (
    DONE,
    HANDOVER_FACTOR,
    OVERTIME_RATE,
    PAUSED,
    REMOVED,
    RUNNING,
    UNSTARTED,
    ActivityStatus,
    InsertedActivity,
    Observation,
    TemporaryWorker,
    nominal_world,
)
from sentinel.simulation.uncertainty import derive_budget
from sentinel.wbs.extract import normalise_name, normalise_role

Severity = Literal["error", "warning"]
Params = tuple[tuple[str, str | int | float], ...]


@dataclass(frozen=True)
class Issue:
    """A problem of a definition, a check-in or an action, as a message key of `messages` with
    its parameters; `where` points at the field or row (e.g. "tasks[2].crew")."""

    code: str
    params: Params = ()
    where: str | None = None
    severity: Severity = "error"

    @property
    def values(self) -> dict[str, str | int | float]:
        return dict(self.params)


def issue(code: str, where: str | None = None, **params: str | int | float) -> Issue:
    return Issue(code, tuple(params.items()), where)


def warning(code: str, where: str | None = None, **params: str | int | float) -> Issue:
    return Issue(code, tuple(params.items()), where, "warning")


class LiveError(Exception):
    """An operation on a live project that is not possible, with its issues."""

    def __init__(self, issues: Sequence[Issue]) -> None:
        super().__init__("; ".join(i.code for i in issues))
        self.issues = tuple(issues)


def errors(issues: Iterable[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]


def role_key(name: str) -> str:
    """The matching form of a role name: case, spacing and a final plural s ignored (11.2)."""
    return normalise_role(name)


# --------------------------------------------------------------------------- definition


def validate_definition(definition: ProjectDefinition) -> list[Issue]:
    """Every issue of a definition (spec section 11.2), errors and warnings."""
    found: list[Issue] = []
    if not definition.name:
        found.append(issue("empty_project_name", "name"))
    roles = _roles(definition)
    found += _team_issues(definition)
    found += _role_cost_issues(definition, roles)
    task_issues = _task_issues(definition, roles)
    found += task_issues
    if definition.deadline is not None:
        if definition.deadline < definition.start:
            found.append(
                issue(
                    "deadline_before_start",
                    "deadline",
                    deadline=definition.deadline.isoformat(),
                    start=definition.start.isoformat(),
                )
            )
        elif not errors(found):
            found += _deadline_issues(definition)
    return found


def _roles(definition: ProjectDefinition) -> dict[str, tuple[str, int]]:
    """Role key -> (display name of its first person, number of people), in order."""
    roles: dict[str, tuple[str, int]] = {}
    for person in definition.team:
        if not person.role:
            continue
        key = role_key(person.role)
        name, count = roles.get(key, (person.role, 0))
        roles[key] = (name, count + 1)
    return roles


def _team_issues(definition: ProjectDefinition) -> list[Issue]:
    found = []
    keys: set[str] = set()
    names: set[str] = set()
    for i, person in enumerate(definition.team):
        where = f"team[{i}]"
        if person.key in keys:
            found.append(issue("duplicate_person_key", where, key=person.key))
        keys.add(person.key)
        if not person.name:
            found.append(issue("empty_person_name", f"{where}.name", key=person.key))
        else:
            folded = normalise_name(person.name)
            if folded in names:
                found.append(issue("duplicate_person_name", f"{where}.name", name=person.name))
            names.add(folded)
        if not person.role:
            found.append(issue("empty_role", f"{where}.role", person=person.name or person.key))
    return found


def _role_cost_issues(
    definition: ProjectDefinition, roles: Mapping[str, tuple[str, int]]
) -> list[Issue]:
    found = []
    seen: set[str] = set()
    for i, cost in enumerate(definition.roles):
        key = role_key(cost.role)
        if key in seen:
            found.append(issue("duplicate_role_cost", f"roles[{i}]", role=cost.role))
        seen.add(key)
        if key not in roles:
            found.append(warning("unused_role_cost", f"roles[{i}]", role=cost.role))
    return found


def _task_issues(
    definition: ProjectDefinition, roles: Mapping[str, tuple[str, int]]
) -> list[Issue]:
    tasks = definition.tasks
    found: list[Issue] = []
    if not tasks:
        return [issue("no_tasks", "tasks")]
    by_key: dict[str, int] = {}
    names: set[str] = set()
    for i, task in enumerate(tasks):
        where = f"tasks[{i}]"
        if task.key in by_key:
            found.append(issue("duplicate_task_key", where, key=task.key))
        by_key.setdefault(task.key, i)
        label = task.name or task.key
        if not task.name:
            found.append(issue("empty_task_name", f"{where}.name", key=task.key))
        else:
            folded = normalise_name(task.name)
            if folded in names:
                found.append(issue("duplicate_task_name", f"{where}.name", name=task.name))
            names.add(folded)
        if task.duration < 1:
            found.append(
                issue("duration_too_short", f"{where}.duration", task=label, duration=task.duration)
            )
        found += _crew_issues(task.crew, roles, label, f"{where}.crew")
    for i, task in enumerate(tasks):
        label = task.name or task.key
        for predecessor in task.predecessors:
            where = f"tasks[{i}].predecessors"
            if predecessor == task.key:
                found.append(issue("self_predecessor", where, task=label))
            elif predecessor not in by_key:
                found.append(
                    issue("unknown_predecessor", where, task=label, predecessor=predecessor)
                )
    found += _cycle_issues(definition, by_key)
    successors: dict[str, list[str]] = {}
    for task in tasks:
        for predecessor in dict.fromkeys(task.predecessors):
            successors.setdefault(predecessor, []).append(task.key)
    for i, task in enumerate(tasks):
        if task.optional and successors.get(task.key):
            follower = tasks[by_key[successors[task.key][0]]]
            found.append(
                issue(
                    "optional_with_successors",
                    f"tasks[{i}].optional",
                    task=task.name or task.key,
                    successor=follower.name or follower.key,
                )
            )
    return found


def _crew_issues(
    crew: Mapping[str, int], roles: Mapping[str, tuple[str, int]], task: str, where: str
) -> list[Issue]:
    found = []
    seen: set[str] = set()
    for role, count in crew.items():
        key = role_key(role)
        if key in seen:
            found.append(issue("duplicate_crew_role", where, task=task, role=role))
        seen.add(key)
        if count < 0:
            found.append(issue("negative_crew", where, task=task, role=role))
        elif count == 0:
            continue
        elif key not in roles:
            found.append(issue("unknown_role", where, task=task, role=role))
        elif count > roles[key][1]:
            found.append(
                issue(
                    "crew_above_team",
                    where,
                    task=task,
                    role=roles[key][0],
                    count=count,
                    capacity=roles[key][1],
                )
            )
    return found


def _cycle_issues(definition: ProjectDefinition, by_key: Mapping[str, int]) -> list[Issue]:
    """One issue per dependency cycle, listed by task name, the first repeated at the end."""
    tasks = definition.tasks
    successors: dict[str, list[str]] = {t.key: [] for t in tasks}
    for task in tasks:
        for predecessor in dict.fromkeys(task.predecessors):
            if predecessor in by_key and predecessor != task.key:
                successors[predecessor].append(task.key)
    found = []
    for component in _strong_components(successors):
        if len(component) < 2:
            continue
        cycle = _cycle_in(component, successors)
        names = [tasks[by_key[k]].name or k for k in cycle]
        found.append(issue("cycle", "tasks", cycle=" → ".join([*names, names[0]])))
    return found


def _strong_components(successors: Mapping[str, list[str]]) -> list[list[str]]:
    """Strongly connected components (Tarjan 1972), iteratively, in a deterministic order."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    counter = 0
    for root in successors:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, i = work.pop()
            if i == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            nexts = successors[node]
            if i < len(nexts):
                work.append((node, i + 1))
                nxt = nexts[i]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                components.append(sorted(component, key=list(successors).index))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return components


def _cycle_in(component: list[str], successors: Mapping[str, list[str]]) -> list[str]:
    """A cycle through the first task of a strongly connected component."""
    members = set(component)
    start = component[0]
    path = [start]
    seen = {start}
    node = start
    while True:
        nexts = [s for s in successors[node] if s in members]
        if start in nexts and len(path) > 1:
            return path
        step = next((s for s in nexts if s not in seen), None)
        if step is None:  # every member reaches the start, so this only ends the walk
            return path
        path.append(step)
        seen.add(step)
        node = step


def _deadline_issues(definition: ProjectDefinition) -> list[Issue]:
    """The deadline before the critical path (D < LB0, spec section 1.4)."""
    assert definition.deadline is not None
    model = build_model(definition, validate=False)
    lb0 = critical_path_lower_bound(model.instance)
    deadline = model.calendar.deadline(definition.deadline)
    if deadline >= lb0:
        return []
    earliest = model.calendar.finish_date(lb0)
    return [
        issue(
            "deadline_before_critical_path",
            "deadline",
            deadline=definition.deadline.isoformat(),
            earliest=earliest.isoformat(),
        )
    ]


@dataclass(frozen=True)
class Model:
    """A definition mapped onto the model (spec section 11.2): the instance, the activity id of
    every task key, the worker id of every person key, role ids by role key with their display
    names, the daily costs c_k, D and B."""

    definition: ProjectDefinition
    instance: ProjectInstance
    calendar: WorkCalendar
    task_ids: Mapping[str, int]
    worker_ids: Mapping[str, int]
    role_ids: Mapping[str, int]
    role_names: tuple[str, ...]
    costs: tuple[float, ...]
    deadline: int | None
    budget: float


def build_model(definition: ProjectDefinition, *, validate: bool = True) -> Model:
    """The model of a definition; with `validate`, a definition with errors raises LiveError."""
    if validate:
        found = errors(validate_definition(definition))
        if found:
            raise LiveError(found)
    roles = _roles(definition)
    role_ids = {key: k for k, key in enumerate(roles)}
    role_names = tuple(name for name, _ in roles.values())
    tasks = definition.tasks
    n = len(tasks)
    task_ids = {task.key: j for j, task in enumerate(tasks, start=1)}
    successors: list[list[int]] = [[] for _ in range(n + 2)]
    for task in tasks:
        j = task_ids[task.key]
        predecessors = sorted({task_ids[p] for p in task.predecessors if p in task_ids} - {j})
        for i in predecessors or [0]:
            successors[i].append(j)
    for j in range(1, n + 1):
        if not successors[j]:
            successors[j].append(n + 1)
    activities = [Activity(id=0, duration=0, demands=(0,) * len(roles), successors=())]
    for task in tasks:
        demands = [0] * len(roles)
        for role, count in task.crew.items():
            if count > 0:
                demands[role_ids[role_key(role)]] += count
        j = task_ids[task.key]
        activities.append(
            Activity(
                id=j,
                duration=task.duration,
                demands=tuple(demands),
                successors=tuple(sorted(successors[j])),
                name=task.name,
            )
        )
    activities[0] = activities[0].model_copy(update={"successors": tuple(sorted(successors[0]))})
    activities.append(Activity(id=n + 1, duration=0, demands=(0,) * len(roles), successors=()))
    capacities = [count for _, count in roles.values()]
    instance = ProjectInstance(
        name=definition.name or "project",
        activities=tuple(activities),
        roles=tuple(
            Role(id=k, name=name, capacity=capacities[k]) for k, name in enumerate(role_names)
        ),
        workers=tuple(
            Worker(id=w, role=role_ids[role_key(p.role)], name=p.name or p.key)
            for w, p in enumerate(definition.team)
        ),
    )
    costs = [1.0] * len(roles)
    for cost in definition.roles:
        key = role_key(cost.role)
        if key in role_ids:
            costs[role_ids[key]] = cost.daily_cost
    calendar = WorkCalendar(definition.start)
    deadline = None if definition.deadline is None else calendar.deadline(definition.deadline)
    budget = definition.budget
    if budget is None:
        pert = definition.settings.pert()
        budget = derive_budget(instance, BUDGET_RESERVE, costs, pert)
    return Model(
        definition=definition,
        instance=instance,
        calendar=calendar,
        task_ids=task_ids,
        worker_ids={p.key: w for w, p in enumerate(definition.team)},
        role_ids=role_ids,
        role_names=role_names,
        costs=tuple(costs),
        deadline=deadline,
        budget=budget,
    )


# --------------------------------------------------------------------------- records


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Baseline(_Record):
    """The baseline plan (spec section 11.3): planned start of every task by key, the sink's
    (the makespan), the method that found it and its effort."""

    starts: dict[str, int]
    makespan: int
    method: Literal["cpsat", "sgs_lft"]
    status: str
    lower_bound: int | None = None
    wall_time_s: float = 0.0


class TaskProgress(_Record):
    """A task's state after a check-in: started (with work done in crew-member days) or done,
    its start, finish and crew (worker keys)."""

    task: str
    status: Literal["started", "done"]
    start: int
    finish: int | None = None
    work: int = Field(ge=0)
    crew: tuple[str, ...] = ()


class AbsenceRecord(_Record):
    """An absence of a person from day `start`, back on day `back` (None: not yet known)."""

    person: str
    start: int = Field(ge=0)
    back: int | None = None

    def covers(self, day: int) -> bool:
        return self.start <= day and (self.back is None or day < self.back)

    @property
    def announced(self) -> int:
        """L_low: the days to the announced return, 1 without one (spec sections 10.2, 11.3)."""
        return 1 if self.back is None else self.back - self.start


class ShockRecord(_Record):
    """A reported work increase: factor F of `task` at work done `work` (crew-member days)."""

    task: str
    work: int
    factor: float = Field(gt=1)
    day: int


class HandoverRecord(_Record):
    """A SUBST handover of an approved action: `added` crew-member days at work done `work`."""

    task: str
    work: int
    added: int
    day: int


class InsertedTask(_Record):
    """A task added at a check-in: inserted after `after` and before `before` (None: the source
    or the sink, spec section 10.2), on `day`, planned to start on `planned` (3.1 e)."""

    key: str
    name: str
    duration: int = Field(ge=1)
    crew: dict[str, int]
    after: str | None
    before: str | None
    day: int
    optional: bool = False
    planned: int


class Temp(_Record):
    """A temporary worker of an approved OVERTIME, hired on day `hired` for [hired, until)."""

    key: str
    name: str
    role: int
    hired: int
    until: int


class CheckinEffects(_Record):
    """What a check-in changes (spec section 11.3), as stored in the event log."""

    date: date
    day: int
    tasks: tuple[TaskProgress, ...] = ()
    absences: tuple[AbsenceRecord, ...] = ()
    shocks: tuple[ShockRecord, ...] = ()
    inserted: tuple[InsertedTask, ...] = ()


class AppliedAction(_Record):
    """An action applied to the project on `day` (spec section 11.5), as stored: the decision,
    and the state it left mapped onto the project (plan, crews, temporary workers, handovers,
    removed tasks)."""

    day: int
    label: str
    kind: str
    decision: Decision
    plan: dict[str, int]
    sink_plan: int
    crews: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    temps: tuple[Temp, ...] = ()
    handovers: tuple[HandoverRecord, ...] = ()
    removed: tuple[str, ...] = ()


TaskState = Literal["unstarted", "started", "done", "removed"]


@dataclass
class Tracked:
    """The tracking state of one task (definition tasks and tasks added at check-ins)."""

    key: str
    planned: int
    state: TaskState = "unstarted"
    start: int | None = None
    finish: int | None = None
    work: int = 0  # crew-member days done, e_j M_j
    crew: tuple[str, ...] = ()
    removed: int | None = None
    crews: list[tuple[int, tuple[str, ...]]] = field(default_factory=list)  # (from day, crew)

    def crew_on(self, day: int) -> tuple[str, ...]:
        """The crew of the task on `day`: its crew from the start, as SUBST changed it."""
        current: tuple[str, ...] = ()
        for first, crew in self.crews:
            if first <= day:
                current = crew
        return current or self.crew


@dataclass
class _Node:
    """A task of the current network: duration, demands, crew size unit M_j (1 without crew),
    predecessors and successors by key (the source and sink left out)."""

    key: str
    name: str
    duration: int
    demands: tuple[int, ...]
    unit: int
    predecessors: list[str] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    optional: bool = False


# --------------------------------------------------------------------------- the project


class LiveProject:
    """The tracking state of a live project (spec section 11), rebuilt from its event log."""

    def __init__(self, definition: ProjectDefinition) -> None:
        self.definition = definition
        self.model: Model | None = None
        self.baseline: Baseline | None = None
        self.day = 0
        self.checkins: list[tuple[date, int]] = []  # (date, day) of every check-in applied
        self.tasks: dict[str, Tracked] = {}
        self.sink_plan = 0
        self.inserted: list[InsertedTask] = []
        self.temps: list[Temp] = []
        self.absences: list[AbsenceRecord] = []
        self.shocks: list[ShockRecord] = []
        self.handovers: list[HandoverRecord] = []
        self.actions: list[AppliedAction] = []

    # ---- definition and baseline

    @property
    def tracking(self) -> bool:
        """Whether tracking started (the first check-in): the structure is fixed (11.2)."""
        return bool(self.checkins)

    def set_definition(self, definition: ProjectDefinition) -> bool:
        """Replace the definition; returns whether the baseline plan was dropped. Once tracking
        started, only names, the deadline, the budget and the settings may change."""
        if self.tracking and definition.structure() != self.definition.structure():
            raise LiveError([issue("structure_frozen")])
        dropped = definition.structure() != self.definition.structure()
        self.definition = definition
        self.model = None
        if dropped and self.baseline is not None:
            self.baseline = None
            self.tasks = {}
            return True
        return False

    def require_model(self) -> Model:
        if self.model is None:
            self.model = build_model(self.definition)
        return self.model

    def set_baseline(self, baseline: Baseline) -> None:
        """Start from a baseline plan; only before tracking (spec section 11.3)."""
        if self.tracking:
            raise LiveError([issue("structure_frozen")])
        self.require_model()
        self.baseline = baseline
        self.tasks = {
            task.key: Tracked(task.key, baseline.starts[task.key]) for task in self.definition.tasks
        }
        self.sink_plan = baseline.makespan

    @property
    def calendar(self) -> WorkCalendar:
        return WorkCalendar(self.definition.start)

    @property
    def finished(self) -> bool:
        return bool(self.tasks) and all(t.state in ("done", "removed") for t in self.tasks.values())

    # ---- the network

    def nodes(self) -> dict[str, _Node]:
        """The current network of tasks by key: definition tasks, then those added at
        check-ins; removed tasks keep no edges (spec section 4 DESCOPE)."""
        model = self.require_model()
        roles = model.role_ids
        nodes: dict[str, _Node] = {}
        for act in model.instance.activities[1:-1]:
            task = self.definition.tasks[act.id - 1]
            nodes[task.key] = _Node(
                task.key,
                task.name,
                act.duration,
                act.demands,
                max(1, sum(act.demands)),
                optional=task.optional,
            )
        for task in self.definition.tasks:
            for predecessor in dict.fromkeys(task.predecessors):
                if predecessor in nodes and predecessor != task.key:
                    nodes[task.key].predecessors.append(predecessor)
                    nodes[predecessor].successors.append(task.key)
        for added in self.inserted:
            demands = [0] * len(roles)
            for role, count in added.crew.items():
                if count > 0:
                    demands[roles[role_key(role)]] += count
            node = _Node(
                added.key,
                added.name,
                added.duration,
                tuple(demands),
                max(1, sum(demands)),
                optional=added.optional,
            )
            nodes[added.key] = node
            if added.after is not None:
                node.predecessors.append(added.after)
                nodes[added.after].successors.append(added.key)
            if added.before is not None:
                node.successors.append(added.before)
                nodes[added.before].predecessors.append(added.key)
        for key, tracked in self.tasks.items():
            if tracked.state == "removed":
                node = nodes[key]
                for predecessor in node.predecessors:
                    nodes[predecessor].successors.remove(key)
                node.predecessors = []
        return nodes

    def activity_ids(self) -> dict[str, int]:
        """The activity id of every task: definition tasks 1..n, added ones n + 2, ...."""
        model = self.require_model()
        ids = dict(model.task_ids)
        first = model.instance.n_activities
        ids.update({added.key: first + i for i, added in enumerate(self.inserted)})
        return ids

    def worker_keys(self) -> list[str]:
        """The key of every worker id: people, then temporary workers."""
        return [p.key for p in self.definition.team] + [temp.key for temp in self.temps]

    def worker_roles(self) -> list[int]:
        model = self.require_model()
        people = [model.role_ids[role_key(p.role)] for p in self.definition.team]
        return people + [temp.role for temp in self.temps]

    def temp_left(self, temp: Temp) -> int | None:
        """The first day `temp` is no longer hired: the end of its window if it is idle then,
        else the finish of the task it is in (None while that task runs; spec section 4)."""
        for tracked in self.tasks.values():
            if (
                temp.key in tracked.crew
                and tracked.start is not None
                and tracked.start < temp.until
                and (tracked.finish is None or tracked.finish > temp.until)
            ):
                return tracked.finish
        return temp.until

    def available(self, temp: Temp, day: int) -> bool:
        """Whether a temporary worker can join a crew on `day` (hired, within its window)."""
        return temp.hired <= day < temp.until

    def absent(self, person: str, day: int) -> AbsenceRecord | None:
        return next((a for a in self.absences if a.person == person and a.covers(day)), None)

    # ---- the observation

    def observation(self) -> Observation:
        """The observation of step 3 of the current day (spec sections 3 and 11.3)."""
        model = self.require_model()
        if self.baseline is None:
            raise LiveError([issue("no_baseline")])
        settings = self.definition.settings
        instance = model.instance
        t = self.day
        nodes = self.nodes()
        ids = self.activity_ids()
        n_act = instance.n_activities + len(self.inserted)
        sink = instance.sink_id
        keys = self.worker_keys()
        worker = {key: w for w, key in enumerate(keys)}
        roles = self.worker_roles()
        n_people = len(self.definition.team)
        temporary = []
        present = [True] * len(keys)
        absent_since: list[int | None] = [None] * len(keys)
        announced: list[int | None] = [None] * len(keys)
        for w, person in enumerate(self.definition.team):
            absence = self.absent(person.key, t)
            if absence is not None:
                present[w] = False
                absent_since[w] = absence.start
                announced[w] = absence.announced
        cost = 0.0
        for i, temp in enumerate(self.temps):
            left = self.temp_left(temp)
            present[n_people + i] = temp.hired <= t and (left is None or left > t)
            paid_until = t if left is None else min(left, t)
            cost += OVERTIME_RATE * model.costs[temp.role] * max(0, paid_until - temp.hired)
            temporary.append(
                TemporaryWorker(
                    id=n_people + i,
                    role=temp.role,
                    hired=temp.hired,
                    until=temp.until,
                    left=left if left is not None and left <= t else None,
                )
            )
        status: list[ActivityStatus] = [UNSTARTED] * n_act
        work_done = [0.0] * n_act
        start: list[int | None] = [None] * n_act
        finish: list[int | None] = [None] * n_act
        assigned: list[tuple[int, ...]] = [()] * n_act
        plan = [0] * n_act
        if t >= 1:
            status[0], start[0], finish[0] = DONE, 0, 0
        plan[sink] = self.sink_plan
        latest = 0
        for key, tracked in self.tasks.items():
            j = ids[key]
            node = nodes[key]
            plan[j] = tracked.planned
            if tracked.state == "removed":
                status[j] = REMOVED
                continue
            if tracked.state == "unstarted":
                continue
            crew = tuple(worker[w] for w in tracked.crew)
            assigned[j] = crew
            start[j] = tracked.start
            work_done[j] = tracked.work / node.unit
            cost += work_done[j] * sum(model.costs[roles[w]] for w in crew if w < n_people)
            if tracked.state == "done":
                status[j] = DONE
                finish[j] = tracked.finish
                latest = max(latest, tracked.finish or 0)
            elif not any(node.demands) or any(present[w] for w in crew):
                status[j] = RUNNING
            else:
                status[j] = PAUSED
        if self.finished:
            status[sink], start[sink], finish[sink] = DONE, latest, latest
        inserted = tuple(
            InsertedActivity(
                id=ids[added.key],
                day=added.day,
                duration=added.duration,
                demands=nodes[added.key].demands,
                predecessor=0 if added.after is None else ids[added.after],
                successor=sink if added.before is None else ids[added.before],
            )
            for added in self.inserted
        )
        optional = sorted(ids[key] for key, node in nodes.items() if node.optional)
        return Observation(
            day=t,
            instance=instance,
            inserted=inserted,
            plan=tuple(plan),
            status=tuple(status),
            work_done=tuple(work_done),
            start=tuple(start),
            finish=tuple(finish),
            assigned=tuple(assigned),
            work_increases=tuple(
                (ids[s.task], s.work / nodes[s.task].unit, s.factor) for s in self.shocks
            ),
            present=tuple(present),
            absent_since=tuple(absent_since),
            announced=tuple(announced),
            cost=cost,
            deadline=model.deadline,
            pert=settings.pert(),
            disruptions=settings.disruption_params(),
            handovers=tuple(
                (ids[h.task], h.work / nodes[h.task].unit, h.added) for h in self.handovers
            ),
            temporary=tuple(temporary),
            budget=model.budget,
            costs=model.costs,
            overtime_costs=tuple(OVERTIME_RATE * c for c in model.costs),
            optional=tuple(optional),
        )

    # ---- check-ins

    def resolve_checkin(self, checkin: CheckIn) -> CheckinEffects:
        """The effects of a check-in on the current state (spec section 11.3), or LiveError with
        every issue found."""
        model = self.require_model()
        if self.baseline is None:
            raise LiveError([issue("no_baseline")])
        if self.finished:
            raise LiveError([issue("project_finished")])
        calendar = model.calendar
        t = calendar.checkin_day(checkin.date)
        if self.checkins and t < self.day:
            last = self.checkins[-1][0]
            raise LiveError([issue("checkin_out_of_order", "date", date=last.isoformat())])
        found: list[Issue] = []
        absences = self._resolve_absences(checkin, found)
        progress = _Progress(self, checkin, t, absences, found)
        tasks = progress.resolve()
        if errors(found):
            raise LiveError(found)
        trial = self.copy()
        trial.apply_checkin(
            CheckinEffects(date=checkin.date, day=t, tasks=tasks, absences=absences)
        )
        shocks = trial._resolve_increases(checkin, found)
        trial.shocks += shocks
        inserted = trial._resolve_new_tasks(checkin.new_tasks, found)
        if errors(found):
            raise LiveError(found)
        effects = CheckinEffects(
            date=checkin.date,
            day=t,
            tasks=tasks,
            absences=absences,
            shocks=tuple(shocks),
            inserted=tuple(inserted),
        )
        self.copy().apply_checkin(effects).check()
        return effects

    def _resolve_absences(self, checkin: CheckIn, found: list[Issue]) -> tuple[AbsenceRecord, ...]:
        calendar = self.calendar
        people = {p.key: p for p in self.definition.team}
        current = {(a.person, a.start): a for a in self.absences}
        new: dict[tuple[str, int], AbsenceRecord] = {}
        for i, report in enumerate(checkin.absences):
            where = f"absences[{i}]"
            person = people.get(report.person)
            if person is None:
                found.append(issue("unknown_person", where, person=report.person))
                continue
            start = max(0, calendar.first(report.first_day))
            back = None if report.return_date is None else calendar.first(report.return_date)
            if back is not None and back <= start:
                found.append(issue("absence_return_before_start", where, person=person.name))
                continue
            record = AbsenceRecord(person=person.key, start=start, back=back)
            others = [
                a
                for (who, first), a in {**current, **new}.items()
                if who == person.key and first != start
            ]
            clash = next((a for a in others if _overlap(a, record)), None)
            if clash is not None:
                found.append(
                    issue(
                        "absence_overlap",
                        where,
                        person=person.name,
                        date=calendar.date_of(clash.start).isoformat(),
                    )
                )
                continue
            new[(person.key, start)] = record
        return tuple(new.values())

    def _resolve_increases(self, checkin: CheckIn, found: list[Issue]) -> list[ShockRecord]:
        """Shocks of the reported work increases, on the state after the check-in's progress
        (spec section 11.3); `+N` days are F = (R + N) / R with R of spec section 5.2."""
        nodes = self.nodes()
        ids = self.activity_ids()
        shocks: list[ShockRecord] = []
        for i, report in enumerate(checkin.increases):
            where = f"increases[{i}]"
            tracked = self.tasks.get(report.task)
            if tracked is None:
                found.append(issue("unknown_task", where, task=report.task))
                continue
            name = nodes[report.task].name
            if tracked.state != "started":
                state = tracked.state if tracked.state != "unstarted" else "not_started"
                found.append(issue("increase_not_in_progress", where, task=name, state=state))
                continue
            if (report.extra_days is None) == (report.factor is None):
                found.append(issue("increase_amount", where, task=name))
                continue
            if report.factor is not None:
                if report.factor <= 1:
                    found.append(issue("increase_factor_above_one", where, task=name))
                    continue
                factor = report.factor
            else:
                assert report.extra_days is not None
                if report.extra_days <= 0:
                    found.append(issue("increase_days_positive", where, task=name))
                    continue
                observation = self.observation()
                world = nominal_world(observation)
                j = ids[report.task]
                remaining = world.remaining[j] / nodes[report.task].unit
                factor = (remaining + report.extra_days) / remaining
            shock = ShockRecord(task=report.task, work=tracked.work, factor=factor, day=self.day)
            shocks.append(shock)
            self.shocks.append(shock)  # a second increase of the task sees the first
        del self.shocks[len(self.shocks) - len(shocks) :]
        return shocks

    def _resolve_new_tasks(
        self, reports: Sequence[NewTaskReport], found: list[Issue]
    ) -> list[InsertedTask]:
        """Tasks added at the check-in, inserted as after -> new -> before (spec 10.2, 11.3)."""
        model = self.require_model()
        roles = {
            key: (model.role_names[k], model.instance.roles[k].capacity)
            for key, k in model.role_ids.items()
        }
        added: list[InsertedTask] = []
        t = self.day
        for i, report in enumerate(reports):
            where = f"new_tasks[{i}]"
            nodes = self.nodes()
            names = {normalise_name(n.name) for n in nodes.values()}
            label = report.name or "?"
            before_count = len(found)
            if not report.name:
                found.append(issue("empty_task_name", f"{where}.name", key=report.key or "?"))
            elif normalise_name(report.name) in names:
                found.append(issue("new_task_name_used", f"{where}.name", name=report.name))
            key = report.key or self._fresh_key()
            if key in nodes:
                found.append(issue("new_task_key_used", f"{where}.key", key=key))
            if report.duration < 1:
                found.append(
                    issue(
                        "duration_too_short",
                        f"{where}.duration",
                        task=label,
                        duration=report.duration,
                    )
                )
            found += _crew_issues(report.crew, roles, label, f"{where}.crew")
            before, after = report.before, report.after
            if before is not None:
                tracked = self.tasks.get(before)
                if tracked is None:
                    found.append(issue("unknown_task", f"{where}.before", task=before))
                elif tracked.state != "unstarted":
                    found.append(
                        issue(
                            "new_task_before_started",
                            f"{where}.before",
                            name=label,
                            before=nodes[before].name,
                        )
                    )
                elif report.optional:
                    found.append(issue("new_task_optional_before", f"{where}.optional", name=label))
            if after is not None:
                tracked = self.tasks.get(after)
                if tracked is None:
                    found.append(issue("unknown_task", f"{where}.after", task=after))
                elif tracked.state == "removed":
                    found.append(issue("task_removed", f"{where}.after", task=nodes[after].name))
                elif (
                    before is not None
                    and before in self.tasks
                    and (after == before or after in _descendants(nodes, before))
                ):
                    found.append(
                        issue(
                            "new_task_after_invalid",
                            f"{where}.after",
                            name=label,
                            after=nodes[after].name,
                            before=nodes[before].name,
                        )
                    )
            if len(found) > before_count:
                continue
            if after is None:
                ready = 0
            else:
                prior = self.tasks[after]
                if prior.state == "done":
                    assert prior.finish is not None
                    ready = prior.finish
                else:
                    ready = prior.planned + nodes[after].duration
            task = InsertedTask(
                key=key,
                name=report.name,
                duration=report.duration,
                crew={role: count for role, count in report.crew.items() if count > 0},
                after=after,
                before=before,
                day=t,
                optional=report.optional,
                planned=max(t + 1, ready),
            )
            added.append(task)
            self.inserted.append(task)
            self.tasks[key] = Tracked(key, task.planned)
        return added

    def _fresh_key(self) -> str:
        n = 1
        while f"N{n}" in self.tasks:
            n += 1
        return f"N{n}"

    def apply_checkin(self, effects: CheckinEffects) -> "LiveProject":
        """Apply the stored effects of a check-in; returns the project."""
        for progress in effects.tasks:
            tracked = self.tasks[progress.task]
            tracked.state = progress.status
            tracked.start = progress.start
            tracked.finish = progress.finish
            tracked.work = progress.work
            if progress.crew != tracked.crew or not tracked.crews:
                tracked.crews = [(progress.start, progress.crew)]
            tracked.crew = progress.crew
        for record in effects.absences:
            self.absences = [
                a for a in self.absences if (a.person, a.start) != (record.person, record.start)
            ]
            self.absences.append(record)
        self.absences.sort(key=lambda a: (a.person, a.start))
        self.shocks += effects.shocks
        for added in effects.inserted:
            if added.key not in self.tasks:
                self.inserted.append(added)
                self.tasks[added.key] = Tracked(added.key, added.planned)
        self.day = effects.day
        self.checkins.append((effects.date, effects.day))
        return self

    # ---- actions

    def resolve_action(self, decision: Decision, label: str, kind: str) -> AppliedAction | str:
        """A decision applied at step 3 of the current day through the engine (`rehearse`,
        spec section 4), mapped onto the project; or the reason the engine rejects it."""
        observation = self.observation()
        after, rejected = rehearse(observation, decision, handover_factor=HANDOVER_FACTOR)
        if rejected:
            return rejected[0].reason
        model = self.require_model()
        ids = self.activity_ids()
        nodes = self.nodes()
        keys = self.worker_keys()
        temps: list[Temp] = []
        for extra in after.temporary[len(self.temps) :]:
            number = 1 + sum(1 for temp in (*self.temps, *temps) if temp.role == extra.role)
            key = f"temp:{len(self.temps) + len(temps) + 1}"  # no person key has a colon
            name = f"Temporary {model.role_names[extra.role]} {number}"
            temps.append(
                Temp(key=key, name=name, role=extra.role, hired=extra.hired, until=extra.until)
            )
            keys.append(key)
        plan = {}
        crews = {}
        removed = []
        for key, tracked in self.tasks.items():
            j = ids[key]
            if after.status[j] == REMOVED and tracked.state != "removed":
                removed.append(key)
            elif after.status[j] == UNSTARTED and after.plan[j] != tracked.planned:
                plan[key] = after.plan[j]
            crew = tuple(keys[w] for w in after.assigned[j])
            if tracked.state == "started" and crew != tracked.crew:
                crews[key] = crew
        by_id = {j: key for key, j in ids.items()}
        handovers = tuple(
            HandoverRecord(
                task=by_id[j],
                work=round(work * nodes[by_id[j]].unit),
                added=added,
                day=self.day,
            )
            for j, work, added in after.handovers[len(observation.handovers) :]
        )
        return AppliedAction(
            day=self.day,
            label=label,
            kind=kind,
            decision=decision,
            plan=plan,
            sink_plan=after.plan[model.instance.sink_id],
            crews=crews,
            temps=tuple(temps),
            handovers=handovers,
            removed=tuple(removed),
        )

    def apply_action(self, action: AppliedAction) -> "LiveProject":
        """Apply a stored action (spec section 11.5); returns the project."""
        self.temps += action.temps
        for key, start in action.plan.items():
            self.tasks[key].planned = start
        self.sink_plan = action.sink_plan
        for key, crew in action.crews.items():
            self.tasks[key].crew = crew
            self.tasks[key].crews.append((action.day, crew))
        self.handovers += action.handovers
        for key in action.removed:
            self.tasks[key].state = "removed"
            self.tasks[key].removed = action.day
        self.actions.append(action)
        return self

    # ---- helpers

    def copy(self) -> "LiveProject":
        return copy.deepcopy(self)

    def check(self) -> None:
        """Raise if the observation is not one the engine could be in (`state_from_observation`
        and the planning view accept it); a guard against mapping errors."""
        # Imported here: the engine's checks are only needed for this guard.
        from sentinel.scheduling.residual import planning_view
        from sentinel.simulation.state import state_from_observation

        observation = self.observation()
        state_from_observation(observation, nominal_world(observation))
        planning_view(observation)


def _overlap(a: AbsenceRecord, b: AbsenceRecord) -> bool:
    a_end = math.inf if a.back is None else a.back
    b_end = math.inf if b.back is None else b.back
    return a.start < b_end and b.start < a_end


def _descendants(nodes: Mapping[str, _Node], key: str) -> set[str]:
    seen: set[str] = set()
    stack = list(nodes[key].successors)
    while stack:
        current = stack.pop()
        if current not in seen:
            seen.add(current)
            stack.extend(nodes[current].successors)
    return seen


def round_half_up(value: float) -> int:
    """`value` rounded half up, ignoring rounding noise below 1e-9."""
    return math.floor(value + 0.5 + 1e-9)


class _Progress:
    """The task reports of a check-in resolved into task states (spec section 11.3)."""

    def __init__(
        self,
        project: LiveProject,
        checkin: CheckIn,
        day: int,
        absences: Sequence[AbsenceRecord],
        found: list[Issue],
    ) -> None:
        self.project = project
        self.checkin = checkin
        self.day = day
        self.found = found
        self.nodes = project.nodes()
        self.calendar = project.calendar
        merged = {(a.person, a.start): a for a in project.absences}
        merged.update({(a.person, a.start): a for a in absences})
        self.absences = list(merged.values())

    def resolve(self) -> tuple[TaskProgress, ...]:
        project, found, calendar, t = self.project, self.found, self.calendar, self.day
        reports: dict[str, tuple[int, TaskReport]] = {}
        for i, report in enumerate(self.checkin.tasks):
            where = f"tasks[{i}]"
            if report.task in reports:
                found.append(issue("duplicate_report", where, task=report.task))
                continue
            if report.task not in project.tasks:
                found.append(issue("unknown_task", where, task=report.task))
                continue
            reports[report.task] = (i, report)
        finishes = {k: s.finish for k, s in project.tasks.items() if s.state == "done"}
        starts: dict[str, tuple[int, TaskReport, int | None]] = {}  # newly started: finish
        updates: dict[str, TaskProgress] = {}
        for key, (i, report) in reports.items():
            where = f"tasks[{i}]"
            tracked = project.tasks[key]
            name = self.nodes[key].name
            if tracked.state == "removed":
                found.append(issue("task_removed", where, task=name))
                continue
            if report.status == "not_started":
                if tracked.state != "unstarted":
                    found.append(self._started_issue(where, name, tracked))
                continue
            if tracked.state == "done":
                again = report.finish if report.status == "done" else None
                if again is not None and calendar.last(again) + 1 == tracked.finish:
                    continue  # reported done again with the same finish date
                assert tracked.finish is not None
                found.append(
                    issue(
                        "already_done",
                        where,
                        task=name,
                        date=calendar.finish_date(tracked.finish).isoformat(),
                    )
                )
                continue
            finish: int | None = None
            if report.status == "done":
                if report.finish is None:
                    found.append(issue("finish_required", f"{where}.finish", task=name))
                    continue
                finish = calendar.last(report.finish) + 1
                if report.finish > self.checkin.date or finish > t:
                    found.append(
                        issue(
                            "finish_after_checkin",
                            f"{where}.finish",
                            task=name,
                            finish=report.finish.isoformat(),
                            date=self.checkin.date.isoformat(),
                        )
                    )
                    continue
                finishes[key] = finish
            elif report.percent is None:
                found.append(issue("percent_required", f"{where}.percent", task=name))
                continue
            elif not 0 <= report.percent < 100:
                found.append(
                    issue("percent_range", f"{where}.percent", task=name, percent=report.percent)
                )
                continue
            if tracked.state == "started":
                assert tracked.start is not None
                if report.start is not None and calendar.first(report.start) != tracked.start:
                    found.append(self._started_issue(f"{where}.start", name, tracked))
                    continue
                if finish is not None and finish <= tracked.start:
                    found.append(
                        issue(
                            "finish_before_start",
                            f"{where}.finish",
                            task=name,
                            finish=calendar.finish_date(finish).isoformat(),
                            start=calendar.date_of(tracked.start).isoformat(),
                        )
                    )
                    continue
                updates[key] = self._progress(key, report, tracked.start, finish, tracked.crew)
            else:
                starts[key] = (i, report, finish)
        self._start_tasks(starts, finishes, updates)
        return tuple(updates[key] for key in project.tasks if key in updates)

    def _started_issue(self, where: str, name: str, tracked: Tracked) -> Issue:
        assert tracked.start is not None
        return issue(
            "already_started",
            where,
            task=name,
            date=self.calendar.date_of(tracked.start).isoformat(),
        )

    def _start_tasks(
        self,
        starts: Mapping[str, tuple[int, TaskReport, int | None]],
        finishes: Mapping[str, int | None],
        updates: dict[str, TaskProgress],
    ) -> None:
        """Starts and crews of the tasks that started since the previous check-in."""
        project, found, calendar = self.project, self.found, self.calendar
        previous = project.day
        chosen: dict[str, int] = {}
        for key, (i, report, finish) in starts.items():
            where = f"tasks[{i}]"
            name = self.nodes[key].name
            last = (self.day if finish is None else finish) - 1
            if last < 0:
                found.append(issue("no_work_before_start", where, task=name))
                continue
            pending = [p for p in self.nodes[key].predecessors if finishes.get(p) is None]
            if pending:
                found.append(
                    issue(
                        "predecessor_not_done",
                        where,
                        task=name,
                        predecessor=self.nodes[pending[0]].name,
                    )
                )
                continue
            ready = max((finishes[p] or 0 for p in self.nodes[key].predecessors), default=0)
            if report.start is not None:
                start = calendar.first(report.start)
                if report.start < project.definition.start:
                    found.append(
                        issue(
                            "start_before_project",
                            f"{where}.start",
                            task=name,
                            start=report.start.isoformat(),
                            project_start=project.definition.start.isoformat(),
                        )
                    )
                    continue
                if start > last:
                    code = "start_after_checkin" if finish is None else "finish_before_start"
                    found.append(
                        issue(
                            code,
                            f"{where}.start",
                            task=name,
                            start=report.start.isoformat(),
                            date=self.checkin.date.isoformat(),
                            finish=calendar.finish_date(finish or 0).isoformat(),
                        )
                    )
                    continue
            else:
                low = max(min(previous, last), ready)
                start = min(max(project.tasks[key].planned, low), last)
            if start < ready:
                blocker = max(self.nodes[key].predecessors, key=lambda p: finishes[p] or 0)
                found.append(
                    issue(
                        "start_before_predecessor",
                        f"{where}.start",
                        task=name,
                        start=calendar.date_of(start).isoformat(),
                        predecessor=self.nodes[blocker].name,
                        finish=calendar.finish_date(ready).isoformat(),
                    )
                )
                continue
            chosen[key] = start
        reserved = self._reservations(finishes)
        ids = project.activity_ids()
        order = sorted(chosen, key=lambda k: (chosen[k], project.tasks[k].planned, ids[k]))
        for key in order:
            i, report, finish = starts[key]
            crew = self._crew(key, chosen[key], report.crew, reserved, f"tasks[{i}].crew")
            if crew is None:
                continue
            for member in crew:
                reserved.append((member, chosen[key], finish, key))
            updates[key] = self._progress(key, report, chosen[key], finish, crew)

    def _reservations(
        self, finishes: Mapping[str, int | None]
    ) -> list[tuple[str, int, int | None, str]]:
        """(worker, from, to, task) of the started tasks' crews, to the finish (None: open)."""
        reserved = []
        for key, tracked in self.project.tasks.items():
            if tracked.state in ("started", "done"):
                assert tracked.start is not None
                end = finishes.get(key, tracked.finish)
                for member in tracked.crew:
                    reserved.append((member, tracked.start, end, key))
        return reserved

    def _crew(
        self,
        key: str,
        start: int,
        named: Sequence[str] | None,
        reserved: Sequence[tuple[str, int, int | None, str]],
        where: str,
    ) -> tuple[str, ...] | None:
        """The crew of a task started on `start`: the named one if valid, else the lowest-id
        idle present workers of each role (spec section 3.1 b); None after an issue."""
        project, found, calendar = self.project, self.found, self.calendar
        node = self.nodes[key]
        model = project.require_model()
        keys = project.worker_keys()
        roles = project.worker_roles()
        temps = {temp.key: temp for temp in project.temps}
        busy = {
            member: task
            for member, first, end, task in reserved
            if first <= start and (end is None or start < end)
        }
        day = calendar.date_of(start).isoformat()
        if named is not None:
            counts = [0] * len(node.demands)
            for member in named:
                if member not in keys:
                    found.append(issue("crew_unknown_member", where, person=member))
                    return None
                if member in busy:
                    found.append(
                        issue(
                            "crew_member_busy",
                            where,
                            person=self._person_name(member),
                            other=self.nodes[busy[member]].name,
                            date=day,
                        )
                    )
                    return None
                if member in temps and not project.available(temps[member], start):
                    found.append(
                        issue("crew_not_hired", where, person=temps[member].name, date=day)
                    )
                    return None
                counts[roles[keys.index(member)]] += 1
            if len(set(named)) != len(named) or tuple(counts) != node.demands:
                found.append(
                    issue(
                        "crew_wrong_roles",
                        where,
                        task=node.name,
                        expected=self._crew_text(node.demands),
                    )
                )
                return None
            return tuple(named)
        crew: list[str] = []
        for k, need in enumerate(node.demands):
            if need == 0:
                continue
            free = []
            for w, member in enumerate(keys):
                if roles[w] != k or member in busy:
                    continue
                if member in temps:
                    if project.available(temps[member], start):
                        free.append(member)
                elif not any(a.person == member and a.covers(start) for a in self.absences):
                    free.append(member)
            if len(free) < need:
                found.append(
                    issue(
                        "no_crew_available",
                        where,
                        task=node.name,
                        role=model.role_names[k],
                        count=need,
                        free=len(free),
                        date=day,
                    )
                )
                return None
            crew += free[:need]
        return tuple(crew)

    def _person_name(self, key: str) -> str:
        for person in self.project.definition.team:
            if person.key == key:
                return person.name
        return next((t.name for t in self.project.temps if t.key == key), key)

    def _crew_text(self, demands: Sequence[int]) -> str:
        names = self.project.require_model().role_names
        return ", ".join(f"{n} × {names[k]}" for k, n in enumerate(demands) if n) or "—"

    def _progress(
        self,
        key: str,
        report: TaskReport,
        start: int,
        finish: int | None,
        crew: tuple[str, ...],
    ) -> TaskProgress:
        """Work done e_j = x p_j prod F, rounded half up to whole crew-member days (11.3)."""
        node = self.nodes[key]
        factors = math.prod(s.factor for s in self.project.shocks if s.task == key)
        total = node.duration * factors * node.unit
        if finish is not None:
            return TaskProgress(
                task=key,
                status="done",
                start=start,
                finish=finish,
                work=round_half_up(total),
                crew=crew,
            )
        assert report.percent is not None
        work = round_half_up(report.percent / 100 * total)
        floor = max(
            [s.work for s in self.project.shocks if s.task == key]
            + [h.work for h in self.project.handovers if h.task == key],
            default=0,
        )
        if work < floor:
            minimum = math.ceil(1000 * floor / total) / 10
            self.found.append(
                issue("progress_below_change", "tasks", task=node.name, minimum=minimum)
            )
        return TaskProgress(task=key, status="started", start=start, work=work, crew=crew)
