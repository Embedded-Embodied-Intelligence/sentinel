"""The application's one comparison against the research deliberation on simulator worlds (WP9d).

Each world (set/instance/scenario) is run to its end with the settings of a simulator project at
autonomy 2, twice on the same seed: Sentinel deciding as in the application (`AppSentinel`, spec
section 11.5) and as in the research runs (`Sentinel`, spec section 6). Prints per world the
makespan C, the working days late, the deliberations and the wall time, then the totals, and
for the application's rule how often each thing the spec's readings turn on happened: a later
component deciding, the sentence of spec section 11.5 item 7 being due (a row shown with a higher
rounded chance), an alternative shown with a higher chance, one of them significantly better
than the choice in a pair (the rule filters against the best of the set, so this can happen), and
a candidate dropped in stage 1 winning. An informal check of what the rule changes, for the WP
report; not a study, nothing is written.

    uv run python scripts/bench_app_rule.py --workers 3 j30/j3026_7/1 j60/j6010_7/1
    uv run python scripts/bench_app_rule.py --workers 3 --limit 15
"""

import argparse
import multiprocessing
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.evaluate import CandidateStats, Evaluator, PairedErrors
from sentinel.agent.params import SentinelParams
from sentinel.app import planning, simulator
from sentinel.app.simulator import PolicyRun, SimulatorSpec, World, build_world
from sentinel.dashboard.world import Observed
from sentinel.policies.base import Policy
from sentinel.policies.sentinel import Sentinel

ROOT = Path("data/psplib")
CACHE = Path("data/derived/baselines")
START = date(2026, 11, 2)
RULES = ("app", "research")
# Spread over the J30 parameter classes; the first five are the simulator test's projects.
WORLDS = (
    "j30/j3026_7/1",
    "j30/j301_1/1",
    "j30/j3010_3/2",
    "j30/j3019_5/3",
    "j30/j3037_9/4",
    "j30/j302_3/0",
    "j30/j306_8/1",
    "j30/j3012_2/2",
    "j30/j3015_6/3",
    "j30/j3021_4/0",
    "j30/j3024_9/1",
    "j30/j3029_1/2",
    "j30/j3033_5/3",
    "j30/j3041_7/0",
    "j30/j3045_10/1",
)
_APP_POLICY = simulator.policy_of


@dataclass(frozen=True)
class Outcome:
    world: str
    rule: str
    makespan: int
    deadline: int
    deliberations: int
    rollouts: int
    seconds: float
    later: int = 0
    sentence: int = 0
    higher: int = 0
    better_in_a_pair: int = 0
    revived: int = 0

    @property
    def late(self) -> int:
        return max(0, self.makespan - self.deadline)


def _research_policy(spec: SimulatorSpec, name: str) -> Policy:
    params = SentinelParams(autonomy=spec.autonomy, deterministic_time_limit=simulator.T_CP)
    return Observed(Sentinel(params, seed=spec.seed))


def _watched(
    run: PolicyRun, evaluators: dict[int, Evaluator], dropped: dict[int, set[str]]
) -> dict[str, int]:
    """The counts of the module docstring over the deliberations of an application run."""
    sentinel = run.sentinel
    assert sentinel is not None
    counts = {"later": 0, "sentence": 0, "higher": 0, "better_in_a_pair": 0, "revived": 0}
    record: DecisionRecord
    for record in sentinel.records:
        if not record.deliberated or not record.candidates:
            continue
        counts["later"] += record.reason in planning.LATER_COMPONENTS
        comparison = sentinel.comparisons[record.day]
        counts["sentence"] += planning.tie_kind(record, comparison, sentinel.params) is not None
        counts["revived"] += record.chosen in dropped.get(record.day, set())
        rows = {c.label: c for c in record.candidates}
        chosen = rows[record.chosen]
        evaluator = evaluators[record.day]
        for impact in comparison.impacts[1:]:
            other = rows[impact.label]
            if other.p_on_time <= chosen.p_on_time:
                continue
            counts["higher"] += 1
            pair = [evaluator.outcomes[chosen.label], evaluator.outcomes[other.label]]
            se = PairedErrors(pair, chosen.rollouts, evaluator.budget)("on_time", 0, 1)
            counts["better_in_a_pair"] += not sentinel.params.ties(
                "on_time", other.capped - chosen.capped, se
            )
    return counts


def run_world(world_name: str, rule: str) -> Outcome:
    """The world run to its end under `rule`."""
    set_name, instance, scenario = world_name.split("/")
    spec = SimulatorSpec(
        set_name=set_name,  # type: ignore[arg-type]
        instance=instance,
        scenario=int(scenario),
        start=START,
    )
    world: World = build_world(spec, ROOT, CACHE)
    simulator.policy_of = _APP_POLICY if rule == "app" else _research_policy
    evaluators: dict[int, Evaluator] = {}
    dropped: dict[int, set[str]] = {}
    compare, stage_one = planning.compare, planning.stage_one

    def keeping(record: DecisionRecord, evaluator: Evaluator) -> planning.Comparison:
        evaluators[record.day] = evaluator
        return compare(record, evaluator)

    def noting(
        evaluator: Evaluator, candidates: Sequence[Candidate], deviations: Sequence[float]
    ) -> list[CandidateStats]:
        stats = stage_one(evaluator, candidates, deviations)
        dropped[evaluator.observation.day] = {s.label for s in stats if s.dropped}
        return stats

    planning.compare, planning.stage_one = keeping, noting
    began = time.perf_counter()
    run = PolicyRun(world, "sentinel")
    run.advance(10_000)
    seconds = time.perf_counter() - began
    planning.compare, planning.stage_one = compare, stage_one
    sentinel = run.sentinel
    assert sentinel is not None
    counts = _watched(run, evaluators, dropped) if rule == "app" else {}
    return Outcome(
        world=world_name,
        rule=rule,
        makespan=run.result().makespan,
        deadline=world.deadline,
        deliberations=sentinel.stats.deliberations,
        rollouts=sentinel.stats.rollouts,
        seconds=seconds,
        **counts,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("worlds", nargs="*", help="set/instance/scenario (default: the list here)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="only the first N worlds")
    args = parser.parse_args()
    worlds = (args.worlds or list(WORLDS))[: args.limit]
    context = multiprocessing.get_context("spawn")
    outcomes: dict[tuple[str, str], Outcome] = {}
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=context) as pool:
        tasks = [pool.submit(run_world, world, rule) for world in worlds for rule in RULES]
        for task in as_completed(tasks):
            outcome = task.result()
            outcomes[(outcome.world, outcome.rule)] = outcome
    print("world | D | app: C, late, deliberations, s | research: C, late, deliberations, s")
    for world in worlds:
        app, research = outcomes[(world, "app")], outcomes[(world, "research")]
        print(
            f"{world} | {app.deadline} | {app.makespan}, {app.late}, {app.deliberations}, "
            f"{app.seconds:.1f} | {research.makespan}, {research.late}, "
            f"{research.deliberations}, {research.seconds:.1f}"
        )
    for rule in RULES:
        found = [outcomes[(world, rule)] for world in worlds]
        print(
            f"{rule}: on time {sum(o.late == 0 for o in found)} of {len(found)}, mean days late "
            f"{sum(o.late for o in found) / len(found):.2f}, mean C "
            f"{sum(o.makespan for o in found) / len(found):.2f}, rollouts "
            f"{sum(o.rollouts for o in found)}, {sum(o.seconds for o in found):.0f} s"
        )
    apps = [outcomes[(world, "app")] for world in worlds]
    print(
        f"app, deliberations {sum(o.deliberations for o in apps)}: a later component decided "
        f"{sum(o.later for o in apps)}, the sentence due {sum(o.sentence for o in apps)}, "
        f"alternatives shown with a higher chance "
        f"{sum(o.higher for o in apps)}, of them significantly better in a pair "
        f"{sum(o.better_in_a_pair for o in apps)}, a dropped candidate won "
        f"{sum(o.revived for o in apps)}"
    )
    pairs = [(outcomes[(world, "app")], outcomes[(world, "research")]) for world in worlds]
    print(
        f"app earlier in {sum(a.makespan < r.makespan for a, r in pairs)}, the same in "
        f"{sum(a.makespan == r.makespan for a, r in pairs)}, later in "
        f"{sum(a.makespan > r.makespan for a, r in pairs)}"
    )


if __name__ == "__main__":
    main()
