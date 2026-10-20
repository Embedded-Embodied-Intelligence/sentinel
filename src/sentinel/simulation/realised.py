"""Static views of a simulated run for the feasibility checks of spec section 1.3."""

from sentinel.model.instance import Activity, ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.simulation.engine import SimulationResult
from sentinel.simulation.events import Absence, NewActivity
from sentinel.simulation.state import WorkSegment


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
    """Instance and schedule of the work segments of a completed run, for `validate_schedule`.

    Every work segment becomes an activity with the segment length as duration and the demands
    of its activity. The segments of one activity are chained, and every precedence of the run
    (D3 insertions included) links the last segment of the predecessor to the first segment of
    the successor. Capacities stay nominal; `execution_violations` checks single workers.
    """
    if result.truncated:
        raise ValueError(f"the run with seed {result.seed} was truncated at {result.max_days}")
    successors, demands = project_graph(instance, result)
    by_activity: list[list[WorkSegment]] = [[] for _ in successors]
    for segment in result.segments:  # sorted by (activity, start)
        by_activity[segment.activity].append(segment)
    sink = instance.sink_id
    order = [0, *(j for j in range(1, len(successors)) if j != sink), sink]
    first = [0] * len(successors)
    last = [0] * len(successors)
    starts: list[int] = []
    durations: list[int] = []
    owner: list[int] = []
    for j in order:
        if not by_activity[j]:
            raise ValueError(f"activity {j} has no work segment")
        first[j] = len(starts)
        for segment in by_activity[j]:
            starts.append(segment.start)
            durations.append(segment.end - segment.start)
            owner.append(j)
        last[j] = len(starts) - 1
    links: list[list[int]] = [[] for _ in starts]
    for j in order:
        for i in range(first[j], last[j]):
            links[i].append(i + 1)
        links[last[j]].extend(first[s] for s in successors[j])
    activities = tuple(
        Activity(id=i, duration=durations[i], demands=demands[owner[i]], successors=tuple(links[i]))
        for i in range(len(starts))
    )
    realised = ProjectInstance(
        name=f"{instance.name}/realised",
        activities=activities,
        roles=instance.roles,
        workers=instance.workers,
        source="simulation",
    )
    return realised, Schedule(starts=tuple(starts))


def execution_violations(instance: ProjectInstance, result: SimulationResult) -> list[str]:
    """Worker-level violations of a run: wrong role counts, double bookings, work while absent."""
    _, demands = project_graph(instance, result)
    role = [worker.role for worker in instance.workers]
    absent: dict[int, set[int]] = {}
    for event in result.events:
        if isinstance(event, Absence):
            absent.setdefault(event.worker, set()).update(
                range(event.day, event.day + event.length)
            )
    working: dict[tuple[int, int], int] = {}
    problems: list[str] = []
    for segment in result.segments:
        j = segment.activity
        if segment.end == segment.start:
            continue
        counts = [0] * len(instance.roles)
        for w in segment.workers:
            counts[role[w]] += 1
        if tuple(counts) != demands[j]:
            problems.append(f"activity {j} works with {counts} workers, demands {demands[j]}")
        for day in range(segment.start, segment.end):
            for w in segment.workers:
                other = working.setdefault((w, day), j)
                if other != j:
                    problems.append(f"worker {w} works on {other} and {j} on day {day}")
                if day in absent.get(w, ()):
                    problems.append(f"worker {w} works on {j} on day {day} while absent")
    return problems
