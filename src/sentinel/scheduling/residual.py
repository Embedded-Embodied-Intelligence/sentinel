"""The planning view of day t and the residual scheduling problem (spec section 4.1).

`planning_view` turns an observation into a `ResidualProblem` under the assumptions of the
deterministic forecaster (spec section 5.2): started activities keep their whole crew until
their estimated finish, absent idle workers stay away until their announced return, and
unstarted activities take their nominal durations. `residual_sgs` schedules the problem with a
serial SGS under release times and a time-varying capacity (Kolisch 1996 generalised);
`sentinel.scheduling.cpsat.solve_residual` solves it with CP-SAT. The module needs no solver,
so the engine can check RESEQ plans without loading OR-Tools. The representation is described
in ADR-0012.
"""

from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, NonNegativeInt, model_validator

from sentinel.model.schedule import Violation
from sentinel.simulation.state import (
    DONE,
    UNSTARTED,
    Observation,
    nominal_activity,
    nominal_world,
)

# Priority of the residual SGS: latest finish times, or a value per activity id (lower first).
Priority = Literal["lft"] | Mapping[int, float]


class ResidualProblem(BaseModel):
    """The rest of a project as a planner sees it on `day` (spec section 4.1).

    Per-activity tuples are indexed by position: `activities[i]` is the id of the i-th
    unstarted activity (increasing ids), `durations[i]` its nominal p_j, `demands[i]` its r_jk
    per role, `successors[i]` the positions of its successors (all unstarted), `fixed_finish[i]`
    the latest finish of its finished (realised F_i) and started (estimated F-hat_i)
    predecessors, 0 without any, and `planned[i]` its start in the current plan. `profile[k]`
    holds the capacity of role k as steps (first day, capacity): the first on `day`, the last
    one lasts for ever and equals `capacities[k]` = R_k. `estimated_finish` lists (id, F-hat_j)
    of the started activities and `sink` is the id of the dummy end, whose start is the
    residual makespan.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    activities: tuple[NonNegativeInt, ...]
    durations: tuple[NonNegativeInt, ...]
    demands: tuple[tuple[NonNegativeInt, ...], ...]
    successors: tuple[tuple[NonNegativeInt, ...], ...]
    fixed_finish: tuple[NonNegativeInt, ...]
    planned: tuple[int, ...]
    capacities: tuple[NonNegativeInt, ...]
    profile: tuple[tuple[tuple[NonNegativeInt, NonNegativeInt], ...], ...]
    estimated_finish: tuple[tuple[NonNegativeInt, NonNegativeInt], ...]
    sink: NonNegativeInt

    @model_validator(mode="after")
    def _check(self) -> Self:
        m = len(self.activities)
        sizes = {len(self.durations), len(self.demands), len(self.successors)}
        if sizes | {len(self.fixed_finish), len(self.planned)} != {m}:
            raise ValueError(f"per-activity fields must all have {m} entries")
        if list(self.activities) != sorted(set(self.activities)):
            raise ValueError("activity ids must be distinct and increasing")
        if self.sink not in self.activities:
            raise ValueError(f"the sink {self.sink} must be unstarted")
        n_roles = len(self.capacities)
        if len(self.profile) != n_roles or any(len(d) != n_roles for d in self.demands):
            raise ValueError(f"need a profile and demands for each of {n_roles} roles")
        if any(q >= m for succ in self.successors for q in succ):
            raise ValueError("successor positions out of range")
        for k, (steps, capacity) in enumerate(zip(self.profile, self.capacities, strict=True)):
            days = [day for day, _ in steps]
            if not steps or days[0] != self.day or days != sorted(set(days)):
                raise ValueError(f"profile of role {k} must start on day {self.day}, increasing")
            if steps[-1][1] != capacity or any(level > capacity for _, level in steps):
                raise ValueError(f"profile of role {k} must stay within and end at {capacity}")
            if any(d[k] > capacity for d in self.demands):
                raise ValueError(f"a demand of role {k} exceeds its capacity {capacity}")
        return self

    def releases(self) -> list[int]:
        """Earliest start of every position: max(day, fixed finish)."""
        day = self.day
        return [max(day, finish) for finish in self.fixed_finish]

    def planned_starts(self) -> dict[int, int]:
        """The current plan of the residual activities, by id."""
        return dict(zip(self.activities, self.planned, strict=True))


def planning_view(observation: Observation) -> ResidualProblem:
    """The residual problem of the observed day (spec section 4.1).

    Started activities reserve their whole crew, absent members included, until their estimated
    finish F-hat_j, their finish in the deterministic forecast (`nominal_world`, no future
    disruptions); absent idle workers are unavailable until their nominal return
    s + max(L_low, t - s + 1). Unstarted activities, D3 ones included, take their nominal
    durations and demands.
    """
    t = observation.day
    instance = observation.instance
    status = observation.status
    n = len(status)
    successors = [list(act.successors) for act in instance.activities]
    for inserted in observation.inserted:
        successors[inserted.predecessor].append(inserted.id)
        successors.append([inserted.successor])
    world = nominal_world(observation)
    present, return_day = observation.present, world.return_day
    roles = [worker.role for worker in instance.workers]
    capacities = tuple(role.capacity for role in instance.roles)
    changes: list[dict[int, int]] = [{} for _ in capacities]  # per role: day -> capacity change
    finish = [0] * n  # realised or estimated finish of every finished or started activity
    estimated: list[tuple[int, int]] = []
    in_crew = [False] * len(present)
    for j, state in enumerate(status):
        if state == DONE:
            done = observation.finish[j]
            if done is None:
                raise ValueError(f"finished activity {j} has no finish")
            finish[j] = done
        elif state != UNSTARTED:
            crew = observation.assigned[j]
            end = _estimated_finish(t, world.remaining[j], crew, present, return_day)
            finish[j] = end
            estimated.append((j, end))
            for w in crew:
                in_crew[w] = True
                _reserve(changes[roles[w]], t, end)
    for w, here in enumerate(present):
        if not here and not in_crew[w]:
            _reserve(changes[roles[w]], t, return_day[w])
    unstarted = [j for j in range(n) if status[j] == UNSTARTED]
    position = {j: i for i, j in enumerate(unstarted)}
    fixed = [0] * len(unstarted)
    links: list[list[int]] = [[] for _ in unstarted]
    for i in range(n):
        for s in successors[i]:
            if s not in position:
                if i in position:
                    raise ValueError(f"activity {s} began before its predecessor {i}")
                continue
            if i in position:
                links[position[i]].append(position[s])
            elif finish[i] > fixed[position[s]]:
                fixed[position[s]] = finish[i]
    durations: list[int] = []
    demands: list[tuple[int, ...]] = []
    for j in unstarted:
        duration, demand = nominal_activity(observation, j)
        durations.append(duration)
        demands.append(demand)
    # Built from a consistent observation, so validation is skipped for speed.
    return ResidualProblem.model_construct(
        day=t,
        activities=tuple(unstarted),
        durations=tuple(durations),
        demands=tuple(demands),
        successors=tuple(tuple(sorted(succ)) for succ in links),
        fixed_finish=tuple(fixed),
        planned=tuple(observation.plan[j] for j in unstarted),
        capacities=capacities,
        profile=tuple(
            _steps(t, cap, change) for cap, change in zip(capacities, changes, strict=True)
        ),
        estimated_finish=tuple(estimated),
        sink=instance.sink_id,
    )


def _reserve(change: dict[int, int], start: int, end: int) -> None:
    """One unit of a role is unavailable on days start .. end - 1."""
    change[start] = change.get(start, 0) - 1
    change[end] = change.get(end, 0) + 1


def _steps(day: int, capacity: int, change: dict[int, int]) -> tuple[tuple[int, int], ...]:
    """Capacity steps (first day, capacity) from `day` on, equal neighbours merged."""
    level = capacity + change.get(day, 0)
    steps = [(day, level)]
    for when in sorted(change):
        if when == day:
            continue
        level += change[when]
        if level != steps[-1][1]:
            steps.append((when, level))
    return tuple(steps)


def _estimated_finish(
    t: int,
    remaining: float,
    crew: Sequence[int],
    present: Sequence[bool],
    return_day: Sequence[int],
) -> int:
    """F-hat_j: the day after the first day from t on whose work exhausts `remaining`.

    Work is in crew-member days, as in the engine: each day the members present that day do one
    unit each (members return on their nominal return day), one unit without demands. The
    subtraction is the engine's own, so the finish equals the deterministic forecast's.
    """
    if not crew:
        rate, returns = 1, []
    else:
        rate = sum(1 for w in crew if present[w])
        returns = sorted(return_day[w] for w in crew if not present[w])
    day, back = t, 0
    while True:
        while back < len(returns) and returns[back] <= day:
            rate += 1
            back += 1
        if rate:
            remaining -= rate
            if remaining <= 0:
                return day + 1
        elif back == len(returns):
            raise ValueError("an activity without present or returning members cannot finish")
        day += 1


def validate_residual(problem: ResidualProblem, starts: Mapping[int, int]) -> list[Violation]:
    """Violations of `starts` (by id) as a solution of the residual problem; empty if feasible.

    Every residual activity needs a start and nothing else may have one ("length"); starts lie
    at or after the day and the fixed finishes of finished and started predecessors
    ("release"); unstarted successors start after their predecessors finish ("precedence"); on
    every day, the demand of the activities in progress fits the role's capacity step
    ("resource"; zero-duration activities occupy no day).
    """
    ids = problem.activities
    violations = [
        Violation(kind="length", activity=j, detail=f"unstarted activity {j} has no start")
        for j in ids
        if j not in starts
    ]
    known = set(ids)
    violations += [
        Violation(kind="length", activity=j, detail=f"activity {j} is not in the residual problem")
        for j in sorted(starts)
        if j not in known
    ]
    if len(violations) > 0:
        return violations
    s = [starts[j] for j in ids]
    durations = problem.durations
    for i, (j, release) in enumerate(zip(ids, problem.releases(), strict=True)):
        if s[i] < release:
            violations.append(
                Violation(
                    kind="release",
                    activity=j,
                    time=s[i],
                    detail=f"activity {j} starts on day {s[i]} before its release {release}",
                )
            )
        for q in problem.successors[i]:
            if s[q] < s[i] + durations[i]:
                violations.append(
                    Violation(
                        kind="precedence",
                        activity=ids[q],
                        time=s[q],
                        detail=f"activity {ids[q]} starts on day {s[q]} before {j} finishes on "
                        f"day {s[i] + durations[i]}",
                    )
                )
    for k, steps in enumerate(problem.profile):
        violations += _overloads(problem, s, k, steps)
    return violations


def _overloads(
    problem: ResidualProblem, s: list[int], k: int, steps: Sequence[tuple[int, int]]
) -> list[Violation]:
    """Days on which the demand for role k exceeds its capacity step."""
    change: dict[int, int] = {}
    for i, (p, demand) in enumerate(zip(problem.durations, problem.demands, strict=True)):
        if p > 0 and demand[k] > 0:
            change[s[i]] = change.get(s[i], 0) + demand[k]
            change[s[i] + p] = change.get(s[i] + p, 0) - demand[k]
    if not change:
        return []
    bounds = {day: level for day, level in steps}
    days = sorted(set(change) | set(bounds))
    violations: list[Violation] = []
    usage, capacity = 0, steps[0][1]
    for start, end in pairwise(days):
        usage += change.get(start, 0)
        capacity = bounds.get(start, capacity)
        if usage <= capacity:
            continue
        for day in range(start, end):
            violations.append(
                Violation(
                    kind="resource",
                    time=day,
                    role=k,
                    detail=f"role {k} on day {day}: demand {usage} exceeds capacity {capacity}",
                )
            )
    return violations


def residual_sgs(problem: ResidualProblem, priority: Priority = "lft") -> dict[int, int]:
    """Serial SGS with release times and a time-varying capacity (Kolisch 1996 generalised).

    Each stage takes the eligible activity (all residual predecessors scheduled) with the lowest
    priority value, ties by smallest id, and starts it on the earliest day at or after its
    release and its predecessors' finishes on which every role it needs has enough free
    capacity for its whole duration. "lft" ranks by latest finish times of the residual network
    (Kolisch 1996); a mapping gives a value per activity id, e.g. planned starts to decode a plan.
    Returns the start of every residual activity by id.
    """
    ids, durations, successors = problem.activities, problem.durations, problem.successors
    m = len(ids)
    if m == 0:
        raise ValueError("the residual problem has no activities")
    if isinstance(priority, str):
        if priority != "lft":
            raise ValueError(f"unknown priority rule {priority!r}")
        tails = _tails(problem)
        keys = [(-float(tail), j) for tail, j in zip(tails, ids, strict=True)]
    else:
        keys = [(float(priority[j]), j) for j in ids]
    t = problem.day
    needs = [tuple((k, r) for k, r in enumerate(demand) if r > 0) for demand in problem.demands]
    waiting = [0] * m
    for succ in successors:
        for q in succ:
            waiting[q] += 1
    ready = [release - t for release in problem.releases()]  # days after t
    eligible = [i for i in range(m) if waiting[i] == 0]
    last_step = max(steps[-1][0] for steps in problem.profile) if problem.profile else t
    horizon = last_step - t + 1 + sum(durations) + max(ready, default=0)
    free = [_free_days(steps, t, horizon) for steps in problem.profile]
    capacities = problem.capacities
    starts = [0] * m
    for _ in range(m):
        i = min(eligible, key=keys.__getitem__)
        eligible.remove(i)
        duration = durations[i]
        start = ready[i]
        if duration > 0 and needs[i]:
            while True:
                end = start + duration
                if end > horizon:
                    horizon = max(end, 2 * horizon)
                    for profile, cap in zip(free, capacities, strict=True):
                        profile.extend([cap] * (horizon - len(profile)))
                conflict = start - 1  # latest day in [start, end) without enough free units
                for k, r in needs[i]:
                    profile = free[k]
                    for day in range(end - 1, conflict, -1):
                        if profile[day] < r:
                            conflict = day
                            break
                if conflict < start:
                    break
                start = conflict + 1
            for k, r in needs[i]:
                profile = free[k]
                for day in range(start, start + duration):
                    profile[day] -= r
        starts[i] = start
        finish = start + duration
        for q in successors[i]:
            if finish > ready[q]:
                ready[q] = finish
            waiting[q] -= 1
            if waiting[q] == 0:
                eligible.append(q)
    return {j: t + start for j, start in zip(ids, starts, strict=True)}


def _tails(problem: ResidualProblem) -> list[int]:
    """Longest path from each activity's finish to the sink: LF_j = T - tail_j (spec 1.4)."""
    successors, durations = problem.successors, problem.durations
    m = len(successors)
    waiting = [0] * m
    for succ in successors:
        for q in succ:
            waiting[q] += 1
    order = [i for i in range(m) if waiting[i] == 0]
    for i in order:  # Kahn's algorithm; `order` grows while it is walked
        for q in successors[i]:
            waiting[q] -= 1
            if waiting[q] == 0:
                order.append(q)
    if len(order) != m:
        raise ValueError("the residual precedence graph has a cycle")
    tails = [0] * m
    for i in reversed(order):
        tails[i] = max((durations[q] + tails[q] for q in successors[i]), default=0)
    return tails


def _free_days(steps: Sequence[tuple[int, int]], t: int, horizon: int) -> list[int]:
    """Free units of a role on days t .. t + horizon - 1 from its capacity steps."""
    free: list[int] = []
    for (start, level), following in zip(steps, [*steps[1:], (t + horizon, 0)], strict=True):
        free += [level] * (min(following[0], t + horizon) - start)
    free += [steps[-1][1]] * (horizon - len(free))
    return free
