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
    """Worker-level violations of a run (spec section 3.1 a-b).

    A crew must match its activity's demands, and no worker may be in two crews at once: a
    crew is reserved from S_j to F_j (to the end of a truncated run), absent members included.
    On each day of a reservation the crew members present that day work and nobody else does:
    no work while absent, no idle present member, no work outside the reservation.
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
    for segment in result.segments:
        j = segment.activity
        for day in range(segment.start, segment.end):
            if (j, day) in worked:
                problems.append(f"activity {j} has two work segments on day {day}")
            worked[j, day] = segment.workers
    reserved: dict[int, list[tuple[int, int, int]]] = {}
    for j, crew in enumerate(result.crews):
        start = result.starts[j]
        if start is None:
            continue
        finish = result.finishes[j]
        end = result.max_days + 1 if finish is None else finish
        counts = [0] * len(instance.roles)
        for w in crew:
            counts[role[w]] += 1
            reserved.setdefault(w, []).append((start, end, j))
        if end > start and tuple(counts) != demands[j]:
            problems.append(f"activity {j} has a crew of {counts} workers, demands {demands[j]}")
        for day in range(start, end):
            here = tuple(w for w in crew if day not in absent.get(w, ()))
            workers = worked.pop((j, day), ())
            if workers != here:
                problems.append(f"activity {j} works with {workers} on day {day}, present {here}")
    for j, day in worked:
        problems.append(f"activity {j} works on day {day} outside its reservation")
    for w, spans in reserved.items():
        for (_, end, i), (start, _, j) in pairwise(sorted(spans)):
            if start < end:
                problems.append(f"worker {w} is in the crews of {i} and {j} on day {start}")
    return problems
