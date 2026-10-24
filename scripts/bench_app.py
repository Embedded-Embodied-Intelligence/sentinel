"""Latency of the application's main operations on 30- and 60-task projects (WP9a report).

For each PSPLIB instance given, a live project is made from it (narrator task names, a roster
of people, the IT roles, start 2026-11-02): the baseline plan is timed, the deadline set to the
finish date of 1.15 times the plan's makespan, and a check-in at the end of day 9 reports every
task the plan finishes by then as done, the running ones in proportion, and one crew member of
a task running since before day 9 absent for a week. On that state the forecast (200 rollouts)
and the recommendation (a Sentinel deliberation with the impacts) are timed. A simulator
project of the same instance (scenario 0, Sentinel at autonomy 2) is advanced 10 days twice
(days 0-9 and 10-19).
Wall times in seconds on this machine; nothing is written.

    uv run python scripts/bench_app.py j30/j301_1 j30/j3010_1 j60/j601_1 j60/j6010_1
"""

import argparse
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

from sentinel.app import planning
from sentinel.app.live import LiveProject, build_model
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    Person,
    ProjectDefinition,
    Task,
    TaskReport,
)
from sentinel.app.simulator import Simulation, SimulatorSpec, build_world
from sentinel.data.psplib_loader import instance_path, load_psplib
from sentinel.experiments.runs import derive_seed
from sentinel.interpret.team import roster
from sentinel.wbs.narrate import activity_names, role_names

START = date(2026, 11, 2)
CHECKIN_DAY = 10  # the check-in at the end of day 9 is the observation of day 10


def definition_of(set_name: str, stem: str, root: Path) -> ProjectDefinition:
    instance = load_psplib(instance_path(set_name, stem, root))
    seed = derive_seed(2026, "names", set_name, stem)
    names = activity_names(instance, seed)
    roles = role_names(instance)
    people = roster(instance, seed)
    team = tuple(Person(key=f"P{m.worker}", name=m.name, role=roles[m.role]) for m in people)
    tasks = []
    real = {a.id for a in instance.activities[1:-1]}
    for act in instance.activities[1:-1]:
        tasks.append(
            Task(
                key=f"T{act.id}",
                name=names[act.id],
                duration=act.duration,
                crew={roles[k]: n for k, n in enumerate(act.demands) if n},
                predecessors=tuple(f"T{i}" for i in instance.predecessors(act.id) if i in real),
            )
        )
    return ProjectDefinition(name=instance.name, start=START, team=team, tasks=tuple(tasks))


def checkin_of(project: LiveProject) -> CheckIn:
    """Progress as planned until the end of day 9, and one running crew member absent."""
    assert project.baseline is not None
    calendar = project.calendar
    nodes = project.nodes()
    reports = []
    running = []
    for key, start in project.baseline.starts.items():
        finish = start + nodes[key].duration
        if finish <= CHECKIN_DAY:
            reports.append(TaskReport(task=key, status="done", finish=calendar.finish_date(finish)))
        elif start < CHECKIN_DAY:
            share = 100 * (CHECKIN_DAY - start) / nodes[key].duration
            reports.append(TaskReport(task=key, status="in_progress", percent=min(99.0, share)))
            if start < CHECKIN_DAY - 1:  # its crew was formed before the absence begins
                running.append(key)
    absences = ()
    checkin = CheckIn(date=calendar.date_of(CHECKIN_DAY - 1), tasks=tuple(reports))
    if running:
        trial = project.copy()
        trial.apply_checkin(trial.resolve_checkin(checkin))
        crew = trial.tasks[running[0]].crew
        if crew:
            first = calendar.date_of(CHECKIN_DAY - 1)
            absences = (
                AbsenceReport(
                    person=crew[0], first_day=first, return_date=first + timedelta(days=7)
                ),
            )
    return checkin.model_copy(update={"absences": absences})


def timed(work):  # type: ignore[no-untyped-def]
    began = time.perf_counter()
    result = work()
    return result, time.perf_counter() - began


def bench(name: str, root: Path, cache: Path) -> dict[str, float]:
    set_name, stem = name.split("/")
    definition = definition_of(set_name, stem, root)
    project = LiveProject(definition)
    baseline, t_plan = timed(lambda: planning.baseline_plan(build_model(definition)))
    project.set_baseline(baseline)
    deadline = project.calendar.finish_date(int(1.15 * baseline.makespan + 0.999))
    project.set_definition(definition.model_copy(update={"deadline": deadline}))
    project.apply_checkin(project.resolve_checkin(checkin_of(project)))
    _, t_forecast = timed(lambda: planning.forecast(project))
    recommendation, t_recommend = timed(lambda: planning.recommend(project))
    spec = SimulatorSpec(set_name=set_name, instance=stem, start=START)  # type: ignore[arg-type]
    simulation = Simulation(build_world(spec, root, cache))
    _, t_first = timed(lambda: simulation.advance(10))
    _, t_second = timed(lambda: simulation.advance(10))
    record = recommendation.record
    print(
        f"{name}: plan {t_plan:.2f} s ({baseline.method}, C={baseline.makespan}), forecast "
        f"{t_forecast:.2f} s, recommend {t_recommend:.2f} s ({record.reason}, "
        f"{record.chosen}, {record.rollouts} rollouts), advance(10) {t_first:.2f} s and "
        f"{t_second:.2f} s",
        flush=True,
    )
    return {
        "plan": t_plan,
        "forecast": t_forecast,
        "recommend": t_recommend,
        "advance 0-9": t_first,
        "advance 10-19": t_second,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("instances", nargs="+", help="e.g. j30/j301_1")
    parser.add_argument("--root", type=Path, default=Path("data/psplib"))
    parser.add_argument("--cache", type=Path, default=Path("data/derived/baselines"))
    args = parser.parse_args()
    rows: dict[str, list[dict[str, float]]] = {}
    for name in args.instances:
        rows.setdefault(name.split("/")[0], []).append(bench(name, args.root, args.cache))
    print("\n| set | n | operation | mean (s) | max (s) |\n| --- | ---: | --- | ---: | ---: |")
    for set_name, results in rows.items():
        for operation in results[0]:
            values = [r[operation] for r in results]
            print(
                f"| {set_name} | {len(values)} | {operation} | {statistics.mean(values):.2f} | "
                f"{max(values):.2f} |"
            )


if __name__ == "__main__":
    main()
