"""Regression: 50 full runs of `simulate` stay bit for bit what they were in WP2b.

`tests/fixtures/engine_regression.json` holds four instances with their plans and, for 50
cases (instance, disruptions, seed, policy, trace, deadline, review period, costs), the SHA-256
of the result and of every observation a recording policy saw. It was first written with the
engine of commit 68ba82a (WP2b), before WP3a split `simulate` into state initialisation and a
run loop, and rewritten in WP4b for spec v1.6, where absence returns became decision epochs:
only the epoch counts, the epoch flags of traced days and the observations a recording policy
sees on return days changed. Observations gained B, c_k and c_OT_k in WP5b (spec v1.8 section
3); the digests leave those three fields out (`V18_FIELDS`), so the fixture still checks every
field it was written with. Regenerate it only for an intended change of the semantics:
`uv run python tests/test_engine_regression.py`.
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from sentinel.model import Activity, ProjectInstance, Role, Schedule, make_workers
from sentinel.policies.base import Decision, Noop
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import PertParams

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engine_regression.json"
V18_FIELDS = {"budget", "costs", "overtime_costs"}  # observation fields added after the fixture

PARAMS = {
    "none": DisruptionParams.none(),
    "primary": DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02),
    "busy": DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1),
    "long": DisruptionParams(lambda_a=0.02, mean_absence=5, lambda_s=0.05, lambda_n=0.05),
}


class Recorder:
    """Non-passive policy that keeps every observation and never intervenes."""

    def __init__(self) -> None:
        self.seen: list[Observation] = []

    def decide(self, observation: Observation) -> Decision:
        self.seen.append(observation)
        return Decision(operations=(Noop(),))


def _instance(
    name: str,
    durations: list[int],
    demands: list[list[int]],
    successors: list[list[int]],
    capacities: list[int],
) -> ProjectInstance:
    roles = tuple(Role(id=k, name=f"R{k + 1}", capacity=c) for k, c in enumerate(capacities))
    activities = tuple(
        Activity(id=j, duration=p, demands=tuple(r), successors=tuple(s))
        for j, (p, r, s) in enumerate(zip(durations, demands, successors, strict=True))
    )
    return ProjectInstance(
        name=name, activities=activities, roles=roles, workers=make_workers(roles)
    )


def _random_instance(name: str, n: int, capacities: list[int], seed: int) -> ProjectInstance:
    """n real activities, up to two later successors each, demands up to the capacities."""
    rng = np.random.default_rng(seed)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(0, 9, size=n).tolist(), 0]
    demands = [[int(rng.integers(0, c + 1)) for c in capacities] for _ in range(n)]
    zero = [0] * len(capacities)
    return _instance(
        name, durations, [zero, *demands, zero], [sorted(s) for s in successors], capacities
    )


def _cases(n_setups: int) -> list[dict[str, Any]]:
    """The 50 cases: every combination of the parameters appears on several instances."""
    cases = []
    for i in range(50):
        cases.append(
            {
                "setup": i % n_setups,
                "params": list(PARAMS)[(i // n_setups) % len(PARAMS)],
                "seed": 101 + 37 * i,
                "recorder": i % 6 == 0,
                "trace": i % 5 == 0,
                "deadline": ("none", "loose", "tight", "truncating")[i % 4 if i % 10 else 3],
                "review_period": 5 if i % 2 else 3,
                "costs": i % 7 == 3,
            }
        )
    return cases


def _deadline(kind: str, planned: int) -> int | None:
    if kind == "none":
        return None
    factor = {"loose": 1.5, "tight": 1.1, "truncating": 0.25}[kind]
    return max(1, math.ceil(factor * planned))


def _digest(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run(instance: ProjectInstance, plan: Schedule, case: dict[str, Any]) -> dict[str, Any]:
    recorder = Recorder() if case["recorder"] else None
    result = simulate(
        instance,
        plan,
        NoReaction() if recorder is None else recorder,
        case["seed"],
        pert=PertParams(),
        disruptions=PARAMS[case["params"]],
        deadline=_deadline(case["deadline"], plan.makespan(instance)),
        review_period=case["review_period"],
        costs=[1.0 + 0.5 * k for k in range(len(instance.roles))] if case["costs"] else None,
        record_trace=case["trace"],
    )
    seen = [
        obs.model_dump(mode="json", exclude=V18_FIELDS)
        for obs in ([] if recorder is None else recorder.seen)
    ]
    return {
        "result": _digest(result.model_dump(mode="json")),
        "observations": _digest(seen),
        "makespan": result.makespan,
        "events": len(result.events),
        "truncated": result.truncated,
    }


def _load() -> tuple[list[tuple[ProjectInstance, Schedule]], list[dict[str, Any]]]:
    data = json.loads(FIXTURE.read_text())
    setups = [
        (ProjectInstance.model_validate(s["instance"]), Schedule(starts=tuple(s["plan"])))
        for s in data["setups"]
    ]
    return setups, data["cases"]


def test_fifty_runs_are_unchanged() -> None:
    setups, cases = _load()
    assert len(cases) == 50
    for i, case in enumerate(cases):
        instance, plan = setups[case["setup"]]
        expected = {key: case[key] for key in ("result", "observations", "makespan", "events")}
        expected["truncated"] = case["truncated"]
        assert _run(instance, plan, case) == expected, f"case {i}: {case}"


def _write() -> None:
    """Write the fixture with the current engine (see the module docstring)."""
    from sentinel.data.psplib_loader import load_psplib
    from sentinel.scheduling.priority_rules import lft_priorities
    from sentinel.scheduling.sgs import serial_sgs

    tiny = load_psplib(FIXTURE.parent / "tiny.sm")
    eight = _instance(
        "eight",
        [0, 3, 2, 0, 2, 2, 4, 0],
        [[0, 0], [1, 0], [1, 1], [0, 0], [2, 1], [1, 1], [0, 1], [0, 0]],
        [[1, 2, 6], [3], [4], [5], [7], [7], [7], []],
        [2, 2],
    )
    instances = [
        tiny,
        eight,
        _random_instance("random20", 20, [3, 4, 5], seed=20),
        _random_instance("random30", 30, [10, 10, 10, 10], seed=30),
    ]
    setups = []
    for inst in instances:
        plan = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
        setups.append((inst, plan))
    cases = []
    for case in _cases(len(setups)):
        instance, plan = setups[case["setup"]]
        outcome = _run(instance, plan, case)
        cases.append({**case, **outcome})
    data = {
        "written_with": "engine of WP4b (spec v1.6: returns are decision epochs); otherwise "
        "as written with commit 68ba82a (WP2b)",
        "setups": [
            {"instance": inst.model_dump(mode="json"), "plan": list(plan.starts)}
            for inst, plan in setups
        ],
        "cases": cases,
    }
    FIXTURE.write_text(json.dumps(data, indent=1) + "\n")
    events = sum(c["events"] for c in cases)
    truncated = sum(c["truncated"] for c in cases)
    print(f"wrote {FIXTURE}: {len(cases)} cases, {events} events, {truncated} truncated")


if __name__ == "__main__":
    _write()
