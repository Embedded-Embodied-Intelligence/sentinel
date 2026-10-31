"""How often the list "What threatens the deadline" changes between consecutive check-ins of QA
run 1 without a related event, by the rule of 1.2.3 (200 futures) and of 1.2.4 (1,000 futures whose
first 200 are the same; WP10, fourth follow-up; spec section 11.4).

Both rules are read on the same states, rebuilt from the event log of the run: the file
docs/qa/run1-events.json (project ids and times left out), which `--data` writes from the data
directory of a new `scripts/qa_run.py run1`. A list is compared with the one the manager last saw
before the check-in, so a decision between the two needs no explaining. A task that enters or leaves
it has a related event if, at that check-in, it started, finished or changed state, grew or is new;
if a direct predecessor or successor grew or is new; or if a person on its crew, or with a role it
needs, went away, came back or was reported away. The control keeps the state and changes only the
seed: the next check-in's, and 10 others for each state. About 3 minutes; prints the tables of the
report and writes docs/qa/threat-stability.json. With the logs of `scripts/qa_run.py run1` at the
two versions, it also checks its lists against what the pages showed.

    uv run python scripts/threat_stability.py [--data DIR] [--pages-before LOG] [--pages-after LOG]
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from re import fullmatch
from typing import Any

from sentinel.app import planning
from sentinel.app.config import AppConfig
from sentinel.app.events import CheckinDone, LiveState, replay
from sentinel.app.live import LiveProject, role_key
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION, EventRow, now
from sentinel.experiments.runs import derive_seed

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "docs" / "qa" / "run1-events.json"
RESULT = ROOT / "docs" / "qa" / "threat-stability.json"
RULES = {"before": 200, "after": 1000}  # the rule of 1.2.3 and of 1.2.4: futures of a list
OTHER_SEEDS = 10  # of the control, for each state
TIMES = ("wall_time_s", "evaluation_s", "generation_s")  # in a payload


@dataclass(frozen=True)
class Step:
    """A check-in of the run: the state last seen before it and the one shown after it."""

    date: str
    event: CheckinDone
    before: LiveState
    after: LiveState


def without_times(value: Any) -> Any:
    """A payload with its wall times at zero: the one thing that differs between two runs."""
    if isinstance(value, dict):
        return {k: 0.0 if k in TIMES else without_times(v) for k, v in value.items()}
    return [without_times(v) for v in value] if isinstance(value, list) else value


def export_events(data: Path) -> None:
    """The event log of a run's data directory as a file, without ids and times."""
    services = Services(AppConfig(data_dir=data, inline_jobs=True))
    services.local_session()
    project = services.projects(LOCAL_SESSION)[0]
    rows = services.store.events(LOCAL_SESSION, project.id)
    log = [{"seq": r.seq, "type": r.type, "payload": without_times(r.payload)} for r in rows]
    EVENTS.write_text(json.dumps(log, ensure_ascii=False, indent=0) + "\n", "utf-8")
    services.close()


def steps_of(rows: Sequence[EventRow]) -> list[Step]:
    """The check-ins of a log; what follows one is its recommendation, with any automatic action."""
    found = []
    for i, row in enumerate(rows):
        if row.type != "checkin":
            continue
        last = i + 1 if i + 1 < len(rows) and rows[i + 1].type == "recommendation" else i
        event = CheckinDone.model_validate(row.payload)
        found.append(
            Step(str(event.effects.date), event, replay(rows[:i]), replay(rows[: last + 1]))
        )
    return found


def listed(project: LiveProject, rollouts: int, seed: int | None = None) -> dict[str, float]:
    """The tasks the page names, by key and in its order, with their correlation; none without a
    late future among the forecast's (spec section 11.4)."""
    if not planning.forecast(project).late:
        return {}
    found = planning.threats(project, rollouts=rollouts, seed=seed)
    return {driver.task: driver.sensitivity for driver in found.drivers}


def reasons(task: str, step: Step) -> list[str]:
    """The events of a check-in related to a task that entered or left the list."""
    before, after = step.before.project, step.after.project
    effects = step.event.effects
    nodes = after.nodes()
    grown = {shock.task for shock in effects.shocks}
    new = {inserted.key for inserted in effects.inserted}
    found = []
    if task in new:
        found.append("new")
    elif before.tasks[task].state != after.tasks[task].state:
        found.append(after.tasks[task].state)
    if task in grown:
        found.append("grew")
    node = nodes.get(task)
    neighbours = set() if node is None else {*node.predecessors, *node.successors}
    if neighbours & (grown | new):
        found.append("neighbour grew or is new")
    day_before, day_after = before.checkins[-1][1], effects.day
    crew = set(after.tasks[task].crew)
    names = after.require_model().role_names
    needed = () if node is None else node.demands
    roles = {role_key(names[k]) for k, demand in enumerate(needed) if demand}
    team = {person.key: role_key(person.role) for person in after.definition.team}
    for absence in after.absences:
        moved = absence in effects.absences or any(
            day is not None and day_before < day <= day_after
            for day in (absence.start, absence.back)
        )
        if moved and (absence.person in crew or team.get(absence.person) in roles):
            found.append("absence")
            break
    return found


def compare(steps: Sequence[Step], rollouts: int) -> dict[str, Any]:
    """The lists of a rule and how each differs from the one last seen before the check-in."""
    transitions = []
    lists = []
    for number, step in enumerate(steps):
        project = step.after.project
        nodes = project.nodes()
        now_listed = listed(project, rollouts)
        lists.append(
            {
                "check_in": step.date,
                "chance": planning.forecast(project).p_on_time,
                "listed": [
                    {"task": nodes[t].name, "sensitivity": round(rho, 6)}
                    for t, rho in now_listed.items()
                ],
            }
        )
        if number == 0:
            continue
        seen = listed(step.before.project, rollouts)
        moves = [
            {"task": nodes[t].name, "move": move, "reasons": reasons(t, step)}
            for move, tasks in (
                ("entered", [t for t in now_listed if t not in seen]),
                ("left", [t for t in seen if t not in now_listed]),
            )
            for t in tasks
        ]
        transitions.append(
            {
                "check_in": step.date,
                "seen": [nodes[t].name for t in seen],
                "listed": [nodes[t].name for t in now_listed],
                "moves": moves,
            }
        )
    return {
        "rollouts": rollouts,
        "lists": lists,
        "transitions": transitions,
        "lists_changed": sum(bool(t["moves"]) for t in transitions),
        "with_unrelated_move": sum(any(not m["reasons"] for m in t["moves"]) for t in transitions),
        "moves": sum(len(t["moves"]) for t in transitions),
        "unrelated_moves": sum(not m["reasons"] for t in transitions for m in t["moves"]),
        "names_per_list": sum(len(entry["listed"]) for entry in lists) / len(lists),
    }


def control(steps: Sequence[Step], rollouts: int) -> dict[str, Any]:
    """The same state with only the seed changed: nothing happened, so any change is noise."""
    next_seed = 0
    for following in steps[1:]:
        project = following.before.project
        seed = planning.forecast_seed(project, following.event.effects.day)
        next_seed += set(listed(project, rollouts)) != set(listed(project, rollouts, seed))
    differing = pairs = 0
    for step in steps:
        project = step.after.project
        base = project.definition.settings.seed
        seeds = [derive_seed(base, "stability", str(i)) for i in range(OTHER_SEEDS)]
        lists = [set(listed(project, rollouts, seed)) for seed in seeds]
        for a, b in pairwise(lists):
            pairs += 1
            differing += a != b
    return {
        "next_seed_changed": next_seed,
        "next_seed_of": len(steps) - 1,
        "other_seeds_differing": differing,
        "other_seeds_of": pairs,
    }


def pages_agree(log: Path, lists: Sequence[dict[str, Any]]) -> str:
    """A QA run's log of what the pages showed against a rule's lists, check-in by check-in."""
    shown = {
        str(moment["step"]).split()[1]: [
            text.split("„")[1].split("”")[0] for text in moment["threats"]
        ]
        for moment in json.loads(log.read_text("utf-8"))
        if moment.get("kind") == "moment" and fullmatch(r"c\d+ [\d-]+", str(moment["step"]))
    }
    same = sum(shown[e["check_in"]] == [x["task"] for x in e["listed"]] for e in lists)
    return f"{log}: {same} of {len(lists)} lists as the pages showed them"


def table(results: dict[str, dict[str, Any]]) -> str:
    """The tables of the report."""
    lines = [
        "| Check-in | 1.2.3 (200 futures) | 1.2.4 (1,000 futures) |",
        "| --- | --- | --- |",
    ]
    before, after = results["before"], results["after"]

    def cell(transition: dict[str, Any]) -> str:
        moves = []
        for move in transition["moves"]:
            sign = "+" if move["move"] == "entered" else "-"
            why = ", ".join(move["reasons"]) or "no related event"
            moves.append(f"{sign} {move['task']} ({why})")
        return "; ".join(moves) or "no change"

    for a, b in zip(before["transitions"], after["transitions"], strict=True):
        lines.append(f"| {a['check_in']} | {cell(a)} | {cell(b)} |")
    lines += ["", "| Check-in | Chance | 1.2.3 | 1.2.4 |", "| --- | --- | --- | --- |"]
    for a, b in zip(before["lists"], after["lists"], strict=True):
        names = [
            ", ".join(f"{x['task']} {x['sensitivity']:.2f}" for x in e["listed"]) or "none"
            for e in (a, b)
        ]
        chance = planning.half_up(100 * a["chance"])
        lines.append(f"| {a['check_in']} | {chance:.0f} % | {names[0]} | {names[1]} |")
    lines += ["", "| Measure | 1.2.3 | 1.2.4 |", "| --- | --- | --- |"]
    n = len(before["transitions"])
    for label, key in (
        (f"Lists that changed, of {n}", "lists_changed"),
        (f"Changes with a task moving without a related event, of {n}", "with_unrelated_move"),
        ("Tasks entering or leaving", "moves"),
        ("... without a related event", "unrelated_moves"),
    ):
        lines.append(f"| {label} | {before[key]} | {after[key]} |")
    lines.append(
        f"| Names per list | {before['names_per_list']:.2f} | {after['names_per_list']:.2f} |"
    )
    b, a = before["control"], after["control"]
    lines.append(
        f"| Same state, the next check-in's seed: list differs, of {b['next_seed_of']} "
        f"| {b['next_seed_changed']} | {a['next_seed_changed']} |"
    )
    lines.append(
        f"| Same state, other seeds: lists differ, of {b['other_seeds_of']} pairs "
        f"| {b['other_seeds_differing']} | {a['other_seeds_differing']} |"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=None, help="a new run's data directory")
    parser.add_argument("--pages-before", type=Path, default=None, help="its log at 1.2.3")
    parser.add_argument("--pages-after", type=Path, default=None, help="its log at 1.2.4")
    args = parser.parse_args()
    if args.data is not None:
        export_events(args.data)
    log = json.loads(EVENTS.read_text("utf-8"))
    rows = [EventRow("run1", e["seq"], e["type"], e["payload"], now()) for e in log]
    steps = steps_of(rows)
    results = {name: compare(steps, rollouts) for name, rollouts in RULES.items()}
    for name, rollouts in RULES.items():
        results[name]["control"] = control(steps, rollouts)
    project = steps[0].after.project
    RESULT.write_text(
        json.dumps(
            {"seed": project.definition.settings.seed, **results}, ensure_ascii=False, indent=1
        )
        + "\n",
        "utf-8",
    )
    print(table(results))
    for name, log in (("before", args.pages_before), ("after", args.pages_after)):
        if log is not None:
            print(pages_agree(log, results[name]["lists"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
