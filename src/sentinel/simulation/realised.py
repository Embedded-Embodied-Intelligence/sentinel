"""Static views of a simulated run for the feasibility checks of spec sections 1.3 and 3.1."""

from itertools import pairwise

from sentinel.model.instance import Activity, ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.simulation.engine import SimulationResult
from sentinel.simulation.events import Absence, NewActivity


def project_graph(
    instance: ProjectInstance, result: SimulationResult
) -> tuple[list[list[int]], list[tuple[int, ...]]]:
    """Successors and demands of every activity of a run, D3 insertions included."""
    successors = [list(act.successors) for act in instance.activities]
    demands = [act.demands for act in instance.activities]
    for event in result.events:
        if isinstance(event, NewActivity):
            if event.activity != len(successors):
                raise ValueError(f"inserted ids out of order at activity {event.activity}")
            successors[event.predecessor].append(event.activity)
            successors.append([event.successor])
            demands.append(event.demands)
    return successors, demands


def realised_instance(
    instance: ProjectInstance, result: SimulationResult
) -> tuple[ProjectInstance, Schedule]:
    """Instance and schedule of a completed run, for `validate_schedule` (spec 1.3, 3.1 a).

    Every activity of the run, D3 insertions included, keeps its demands and gets the duration
    F_j - S_j: its crew is reserved from start to finish, absent members included, so the
    capacity check counts them. The sink is renumbered last. Capacities stay nominal;
    `execution_violations` checks single workers.
    """
    if result.truncated:
        raise ValueError(f"the run with seed {result.seed} was truncated at {result.max_days}")
    successors, demands = project_graph(instance, result)
    sink = instance.sink_id
    order = [0, *(j for j in range(1, len(successors)) if j != sink), sink]
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
    realised = ProjectInstance(
        name=f"{instance.name}/realised",
        activities=tuple(activities),
        roles=instance.roles,
        workers=instance.workers,
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
    present member, no work outside the reservation. A RESEQ plan that failed
    `validate_residual` is a violation too.
    """
    _, demands = project_graph(instance, result)
    role = [worker.role for worker in instance.workers]
    absent: dict[int, set[int]] = {}
    for event in result.events:
        if isinstance(event, Absence):
            absent.setdefault(event.worker, set()).update(
                range(event.day, event.day + event.length)
            )
    worked: dict[tuple[int, int], tuple[int, ...]] = {}  # (activity, day) -> who worked
    problems: list[str] = []
    if result.infeasible_reseqs:
        problems.append(f"{result.infeasible_reseqs} RESEQ plans failed validate_residual")
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
    return problems
