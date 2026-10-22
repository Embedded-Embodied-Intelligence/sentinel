"""Rollout budget of Sentinel: cheaper choices against a reference with N = 800 (WP5b, task 3).

Usage:
    uv run python scripts/bench_rollout_budget.py [--runs j30:10 --runs j60:5] [--workers 4]
        [--reference 800] [--csv path]

Sentinel `full` with full autonomy (Lambda = 3) runs at lambda_A = 0.01 (E[L] = 3, lambda_S =
0.01, lambda_N = 0.02, T_r = 5, D = ceil(1.2 C*), `cpsat_det` plans, WP2b seed of replication
0) on `--runs set:instances` spread instances (every (480 / instances)-th). At every
deliberation the probe evaluates NOOP and, unless every needs gate is met, all rule candidates
on the same `--reference` sampled worlds; rollouts are cached by candidate, so the choice of
each budget (N_1, N) in {(25, 100), (50, 200)} is the one a fresh Sentinel with that budget
makes on the first N worlds (needs gate, racing, rule), and the reference choice is the rule on
all candidates with N = `--reference` and no racing. The world follows the (50, 200) choice.
Per budget: agreement with the reference choice, and the losses of its choice in the
reference statistics: p = p_ref(reference choice) - p_ref(choice) and T = T_ref(choice) -
T_ref(reference choice), in days; with the rollouts a fresh Sentinel would run. Decision rule
of the WP5b prompt: adopt (25, 100) if its mean T loss <= 0.25 day and its mean p loss <= 0.01.
Prints Markdown; `--csv` writes one row per deliberation.
"""

import argparse
import csv
import multiprocessing
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from bench_policies import REFERENCE, parse_sizes, spread

from sentinel.agent.candidates import Candidate, generate, noop
from sentinel.agent.decide import DecisionRecord, assess_needs, choose
from sentinel.agent.evaluate import Evaluation, Evaluator, race
from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import DEFAULT_ROOT, instance_path, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.policy_runs import WP2B_BASELINE, check_run
from sentinel.experiments.runs import derive_seed
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.baselines import DEFAULT_CACHE_ROOT, cached_baseline
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import PertParams, derive_deadline

BUDGETS = ((25, 100), (50, 200))
WORLD = (50, 200)  # the budget whose choice the world follows
PARAMS = SentinelParams(autonomy=3, n_stage1=WORLD[0], n_rollouts=WORLD[1])


@dataclass(frozen=True)
class Sample:
    """One deliberation: per budget its choice, reason, the reference p and T of the choice and
    the rollouts a fresh Sentinel with that budget runs; the reference choice and statistics."""

    set_name: str
    instance: str
    day: int
    candidates: int
    reference: str
    reference_p: float
    reference_t: float
    choice_100: str
    reason_100: str
    p_100: float
    t_100: float
    rollouts_100: int
    choice_200: str
    reason_200: str
    p_200: float
    t_200: float
    rollouts_200: int
    probe_s: float


class Probe(Sentinel):
    """Sentinel whose deliberations also compute the choices of every budget and of the
    reference on the same worlds; the world takes the (50, 200) choice."""

    def __init__(self, seed: int, reference: int, where: tuple[str, str]) -> None:
        super().__init__(PARAMS, seed=seed, keep_records=False)
        self.reference = reference
        self.where = where
        self.samples: list[Sample] = []

    def deliberate(self, observation: Observation, discarded: str | None = None) -> DecisionRecord:
        began = time.perf_counter()
        params, n_ref = self.params, self.reference
        t = observation.day
        self.stats.deliberations += 1
        evaluator = Evaluator(observation, derive_seed(self.seed, "sentinel", str(t)), params)
        base = noop(observation)
        evaluator.extend(base, n_ref)
        gates = {b: assess_needs(evaluator, base, stage1=b[0], rollouts=b[1]) for b in BUDGETS}
        reference_gate = assess_needs(evaluator, base, stage1=n_ref, rollouts=n_ref)
        candidates: list[Candidate] = [base]
        if not (reference_gate.met and all(g.met for g in gates.values())):
            candidates = list(generate(observation, params=params).candidates)
        for candidate in candidates:
            evaluator.extend(candidate, n_ref)
        full = race(evaluator, candidates, racing=False, rollouts=n_ref)
        p_ref = {s.label: s.p_on_time for s in full.stats}
        t_ref = {s.label: s.tardiness for s in full.stats}
        reference = _choice(candidates, full, params, reference_gate.met)[0]
        picked: dict[tuple[int, int], tuple[str, str, int]] = {}
        for budget in BUDGETS:
            n1, n = budget
            if gates[budget].met or len(candidates) == 1:
                label, reason = "NOOP", "needs_met" if gates[budget].met else "only_candidate"
                rollouts = gates[budget].rollouts
            else:
                evaluation = race(evaluator, candidates, stage1=n1, rollouts=n)
                label, reason = _choice(candidates, evaluation, params, False)
                counts = {s.label: s.rollouts for s in evaluation.stats}
                counts["NOOP"] = max(counts["NOOP"], gates[budget].rollouts)
                rollouts = sum(counts.values())
            picked[budget] = (label, reason, rollouts)
        self.samples.append(
            Sample(
                set_name=self.where[0],
                instance=self.where[1],
                day=t,
                candidates=len(candidates),
                reference=reference,
                reference_p=p_ref[reference],
                reference_t=t_ref[reference],
                choice_100=picked[BUDGETS[0]][0],
                reason_100=picked[BUDGETS[0]][1],
                p_100=p_ref[picked[BUDGETS[0]][0]],
                t_100=t_ref[picked[BUDGETS[0]][0]],
                rollouts_100=picked[BUDGETS[0]][2],
                choice_200=picked[BUDGETS[1]][0],
                reason_200=picked[BUDGETS[1]][1],
                p_200=p_ref[picked[BUDGETS[1]][0]],
                t_200=t_ref[picked[BUDGETS[1]][0]],
                rollouts_200=picked[BUDGETS[1]][2],
                probe_s=time.perf_counter() - began,
            )
        )
        chosen = next(c for c in candidates if c.label == picked[WORLD][0])
        return DecisionRecord(
            day=t,
            deliberated=True,
            rule=params.rule,
            reason=picked[WORLD][1],  # type: ignore[arg-type]
            chosen=chosen.label,
            decision=chosen.decision,
        )


def _choice(
    candidates: Sequence[Candidate], evaluation: Evaluation, params: SentinelParams, met: bool
) -> tuple[str, str]:
    """The label and reason of the rule's choice (NOOP if the needs gate is met)."""
    if met or len(candidates) == 1:
        return "NOOP", "needs_met" if met else "only_candidate"
    choice = choose(evaluation.stats, params, evaluation.paired)
    return candidates[choice.index].label, choice.reason


def probe_run(job: tuple[str, str, int, int, Path]) -> tuple[list[Sample], float]:
    """One Sentinel run with the probe (in a worker process); its samples and wall time."""
    set_name, stem, c_star, reference, root = job
    instance = load_psplib(instance_path(set_name, stem, root))
    plan = cached_baseline(instance, WP2B_BASELINE, DEFAULT_CACHE_ROOT)[0]
    seed = derive_seed(2026, set_name, stem, "0")
    probe = Probe(seed, reference, (set_name, stem))
    began = time.perf_counter()
    result = simulate(
        instance,
        plan.schedule,
        probe,
        seed,
        pert=PertParams(),
        disruptions=DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02),
        deadline=derive_deadline(c_star, 0.2),
        debug=True,
    )
    check_run(instance, result, f"{instance.name}, budget probe")
    return probe.samples, time.perf_counter() - began


def report(samples: Sequence[Sample], reference: int) -> None:
    print(
        "| Set | Budget (N_1, N) | Deliberations | Agreement % | Mean p loss | Mean T loss d | "
        "p loss > 0 % | T loss > 0.5 d % | Max T loss d | Rollouts / deliberation |"
    )
    print("| --- | --- |" + " ---: |" * 8)
    groups = [(s, [x for x in samples if x.set_name == s]) for s in ("j30", "j60")]
    groups.append(("all", list(samples)))
    for name, group in groups:
        if not group:
            continue
        for suffix, budget in (("100", BUDGETS[0]), ("200", BUDGETS[1])):
            agree = [getattr(x, f"choice_{suffix}") == x.reference for x in group]
            p_loss = [x.reference_p - getattr(x, f"p_{suffix}") for x in group]
            t_loss = [getattr(x, f"t_{suffix}") - x.reference_t for x in group]
            rollouts = [getattr(x, f"rollouts_{suffix}") for x in group]
            print(
                f"| {name.upper()} | {budget} | {len(group)} | "
                f"{100 * statistics.mean(agree):.1f} | "
                f"{statistics.mean(p_loss):.4f} | {statistics.mean(t_loss):.3f} | "
                f"{100 * statistics.mean(v > 0 for v in p_loss):.1f} | "
                f"{100 * statistics.mean(v > 0.5 for v in t_loss):.1f} | {max(t_loss):.2f} | "
                f"{statistics.mean(rollouts):.0f} |"
            )
    evaluated = [x for x in samples if x.candidates > 1]
    print(
        f"\n- reference: all candidates on N = {reference} worlds without racing; "
        f"{len(evaluated)} of {len(samples)} deliberations generated candidates "
        f"(mean {statistics.mean(x.candidates for x in evaluated):.2f} with NOOP)."
        if evaluated
        else ""
    )
    cheap = [(x.reference_p - x.p_100, x.t_100 - x.reference_t) for x in samples]
    p_loss = statistics.mean(v[0] for v in cheap)
    t_loss = statistics.mean(v[1] for v in cheap)
    adopt = t_loss <= 0.25 and p_loss <= 0.01
    print(
        f"- decision: (25, 100) has mean T loss {t_loss:.3f} d (limit 0.25) and mean p loss "
        f"{p_loss:.4f} (limit 0.01): {'adopt (25, 100)' if adopt else 'keep (50, 200)'}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", action="append", default=[], help="set:instances")
    parser.add_argument("--reference", type=int, default=800)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args()
    sizes = parse_sizes(args.runs or ["j30:10:1", "j60:5:1"])
    jobs = []
    for set_name, count, _ in sizes:
        references = load_reference(set_name, REFERENCE[set_name], args.root)  # type: ignore[arg-type]
        for stem in spread(set_name, count, args.root):
            c_star = references[f"{set_name}/{stem}"]
            jobs.append((set_name, stem, c_star, args.reference, args.root))
    jobs.sort(key=lambda job: job[0] != "j60")  # long J60 runs first
    began = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=context) as pool:
        done = list(pool.map(probe_run, jobs))
    samples = [s for found, _ in done for s in found]
    samples.sort(key=lambda s: (s.set_name, s.instance, s.day))
    report(samples, args.reference)
    print(
        f"- {len(jobs)} runs, {len(samples)} deliberations in {time.perf_counter() - began:.0f} s "
        f"wall with {args.workers} workers ({sum(w for _, w in done):.0f} s of run time)."
    )
    if args.csv is not None:
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(samples[0])))
            writer.writeheader()
            writer.writerows(asdict(s) for s in samples)


if __name__ == "__main__":
    main()
