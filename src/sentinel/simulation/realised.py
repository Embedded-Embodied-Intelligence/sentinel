"""Static views of a simulated run for the feasibility checks of spec sections 1.3 and 3.1."""

from itertools import pairwise

from sentinel.model.instance import Activity, ProjectInstance, Role, Worker
from sentinel.model.schedule import Schedule
from sentinel.simulation.engine import Descoped, SimulationResult
from sentinel.simulation.events import Absence, NewActivity
from sentinel.simulation.state import cut_activity


def project_graph(
    instance: ProjectInstance, result: SimulationResult
) -> tuple[list[list[int]], list[tuple[int, ...]]]:
    """Successors and demands of every activity of a run: the D3 insertions and the DESCOPE
    removals in the order they happened (an insertion of step 1 before a removal of step 3 on
    the same day), so the graph is the engine's (spec sections 2.2 and 4)."""
    successors = [list(act.successors) for act in instance.activities]
    demands = [act.demands for act in instance.activities]
    changes: list[tuple[int, int, NewActivity | Descoped]] = [
        (event.day, 0, event) for event in result.events if isinstance(event, NewActivity)
    ]
    changes += [(removal.day, 1, removal) for removal in result.descoped]
    changes.sort(key=lambda change: change[:2])  # stable: insertions keep their order
    for _, _, change in changes:
        if isinstance(change, Descoped):
            cut_activity(successors, change.activity, instance.sink_id)
            continue
        if change.activity != len(successors):
            raise ValueError(f"inserted ids out of order at activity {change.activity}")
        successors[change.predecessor].append(change.activity)
        successors.append([change.successor])
        demands.append(change.demands)
    return successors, demands


def realised_instance(
    instance: ProjectInstance, result: SimulationResult
) -> tuple[ProjectInstance, Schedule]:
    """Instance and schedule of a completed run, for `validate_schedule` (spec 1.3, 3.1 a).

    Every activity of the run, D3 insertions included, keeps its demands and gets the duration
    F_j - S_j: its crew is reserved from start to finish, absent members included, so the
    capacity check counts them. The sink is renumbered last. Capacities are nominal plus every
    temporary worker the run hired (spec section 4 OVERTIME), a bound over the whole run;
    `execution_violations` checks single workers and the capacity of each day. Activities
    removed by DESCOPE are left out, with their edges (spec section 4).
    """
    if result.truncated:
        raise ValueError(f"the run with seed {result.seed} was truncated at {result.max_days}")
    successors, demands = project_graph(instance, result)
    sink = instance.sink_id
    removed = {removal.activity for removal in result.descoped}
    kept = (j for j in range(1, len(successors)) if j != sink and j not in removed)
    order = [0, *kept, sink]
    new_id = {j: i for i, j in enumerate(order)}
    activities: list[Activity] = []
    starts: list[int] = []
    for i, j in enumerate(order):
        start, finish = result.starts[j], result.finishes[j]
        if start is None or finish is None:
            raise ValueError(f"activity {j} did not complete")
        links = tuple(new_id[s] for s in successors[j])
        activities.append(
            Activity(id=i, duration=finish - start, demands=demands[j], successors=links)
        )
        starts.append(start)
    roles, workers = instance.roles, instance.workers
    if result.temporary:
        extra = [0] * len(roles)
        for temp in result.temporary:
            extra[temp.role] += 1
        roles = tuple(
            Role(id=role.id, name=role.name, capacity=role.capacity + extra[role.id])
            for role in roles
        )
        workers += tuple(
            Worker(id=temp.id, role=temp.role, name=f"temporary-{temp.id}")
            for temp in result.temporary
        )
    realised = ProjectInstance(
        name=f"{instance.name}/realised",
        activities=tuple(activities),
        roles=roles,
        workers=workers,
        source="simulation",
    )
    return realised, Schedule(starts=tuple(starts))


def execution_violations(instance: ProjectInstance, result: SimulationResult) -> list[str]:
    """Worker-level violations of a run (spec sections 3.1 a-b and 4).

    A crew must match its activity's demands, and no worker may be in two crews on the same
    day: a crew is reserved from S_j to F_j (to the end of a truncated run), absent members
    included. A SUBST on day d replaces absent members by idle present workers of the same role
    in their slots, from day d on, so a crew never exceeds M_j. On each day of a reservation
    the crew members present that day work and nobody else does: no work while absent, no idle
    present member, no work outside the reservation. A RESEQ or SHIFT plan that failed its
    check is a violation too. A temporary worker (spec section 4 OVERTIME) is never absent, is
    in a crew only while it is hired and joins one only during its window; on every day, the
    crews of a role need at most R_k plus its temporary workers hired that day.
    """
    _, demands = project_graph(instance, result)
    role = [worker.role for worker in instance.workers]
    role += [temp.role for temp in result.temporary]
    first_temporary = len(instance.workers)
    absent: dict[int, set[int]] = {}
    problems: list[str] = []
    for event in result.events:
        if isinstance(event, Absence):
            absent.setdefault(event.worker, set()).update(
                range(event.day, event.day + event.length)
            )
            if event.worker >= first_temporary:
                problems.append(f"temporary worker {event.worker} is absent on day {event.day}")
    worked: dict[tuple[int, int], tuple[int, ...]] = {}  # (activity, day) -> who worked
    if result.infeasible_reseqs:
        problems.append(f"{result.infeasible_reseqs} RESEQ or SHIFT plans failed their check")
    for segment in result.segments:
        j = segment.activity
        for day in range(segment.start, segment.end):
            if (j, day) in worked:
                problems.append(f"activity {j} has two work segments on day {day}")
            worked[j, day] = segment.workers
    changes: dict[int, list[tuple[int, int, int]]] = {}  # activity -> (day, replaced, substitute)
    for sub in result.substitutions:
        for old, new in zip(sub.replaced, sub.workers, strict=True):
            changes.setdefault(sub.activity, []).append((sub.day, old, new))
            if role[old] != role[new]:
                problems.append(f"activity {sub.activity}: {new} replaced {old} of another role")
            if sub.day not in absent.get(old, ()):
                problems.append(f"activity {sub.activity}: {old} was present when replaced")
            if sub.day in absent.get(new, ()):
                problems.append(f"activity {sub.activity}: substitute {new} was absent")
    reserved: dict[int, list[tuple[int, int, int]]] = {}  # worker -> (first day, end, activity)
    for j, final in enumerate(result.crews):
        start = result.starts[j]
        if start is None:
            continue
        finish = result.finishes[j]
        end = result.max_days + 1 if finish is None else finish
        crew = list(final)
        for _, old, new in reversed(changes.get(j, [])):
            crew[crew.index(new)] = old  # the substitute had taken the replaced member's slot
        counts = [0] * len(instance.roles)
        for w in crew:
            counts[role[w]] += 1
        if end > start and tuple(counts) != demands[j]:
            problems.append(f"activity {j} has a crew of {counts} workers, demands {demands[j]}")
        joined = dict.fromkeys(crew, start)  # member -> first day of the current membership
        pending = sorted(changes.get(j, []))
        for day in range(start, end):
            while pending and pending[0][0] <= day:
                _, old, new = pending.pop(0)
                reserved.setdefault(old, []).append((joined.pop(old), day, j))
                crew[crew.index(old)] = new
                joined[new] = day
            here = tuple(w for w in crew if day not in absent.get(w, ()))
            workers = worked.pop((j, day), ())
            if workers != here:
                problems.append(f"activity {j} works with {workers} on day {day}, present {here}")
        if pending:
            problems.append(f"activity {j} has substitutions outside its reservation")
        for w, first in joined.items():
            reserved.setdefault(w, []).append((first, end, j))
    for j, day in worked:
        problems.append(f"activity {j} works on day {day} outside its reservation")
    for w, spans in reserved.items():
        for (_, end, i), (start, _, j) in pairwise(sorted(spans)):
            if start < end:
                problems.append(f"worker {w} is in the crews of {i} and {j} on day {start}")
    if result.temporary:
        problems += _temporary_violations(instance, result, reserved, demands)
    return problems


def _temporary_violations(
    instance: ProjectInstance,
    result: SimulationResult,
    reserved: dict[int, list[tuple[int, int, int]]],
    demands: list[tuple[int, ...]],
) -> list[str]:
    """Temporary workers in crews only while hired, joining only in their window, and the crews
    of each role within R_k plus the temporary workers hired that day (spec section 4)."""
    problems: list[str] = []
    end_of_run = result.max_days + 1
    hired: dict[tuple[int, int], int] = {}  # (role, day) -> temporary workers hired
    for temp in result.temporary:
        gone = end_of_run if temp.left is None else temp.left
        for day in range(temp.hired, gone):
            hired[temp.role, day] = hired.get((temp.role, day), 0) + 1
        for first, end, j in reserved.get(temp.id, ()):
            if first < temp.hired or end > gone:
                problems.append(
                    f"temporary worker {temp.id} is in the crew of {j} on days {first}..{end - 1} "
                    f"but hired on days {temp.hired}..{gone - 1}"
                )
            if first >= temp.until:
                problems.append(
                    f"temporary worker {temp.id} joined the crew of {j} on day {first}, after "
                    f"its window ended on day {temp.until}"
                )
    used: dict[tuple[int, int], int] = {}  # (role, day) -> crew members reserved
    for j, start in enumerate(result.starts):
        if start is None:
            continue
        finish = result.finishes[j]
        for day in range(start, end_of_run if finish is None else finish):
            for k, r in enumerate(demands[j]):
                if r:
                    used[k, day] = used.get((k, day), 0) + r
    for (k, day), units in sorted(used.items()):
        capacity = instance.roles[k].capacity + hired.get((k, day), 0)
        if units > capacity:
            problems.append(f"role {k} on day {day}: crews need {units} of {capacity} workers")
    return problems
