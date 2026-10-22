"""Summaries of a policy study run (WP4b, WP5b; RQ4), generated from its results files only.

Writes `summary.md` with every statistic, the LaTeX table `<table>.tex` (pooled per set and
policy; one more per further reference policy), the figures and `summary_manifest.json`
(provenance as in ADR-0011). Without Sentinel variants the figures are `<figure_prefix>_ontime`
(on time against lambda_A, one line per policy, a column of panels per set and a row per
delta_D) and `<figure_prefix>_tradeoff` (on time against realised deviation, one point per
policy and lambda_A, a row of panels per set with one panel per policy against the reference
policy); with them, `<figure_prefix>_tradeoff` (on time against realised deviation and against
nervousness, pooled per policy, a column of panels per set, the Sentinel variants in colour and
the baselines in grey) and `<figure_prefix>_actions` (the share of deliberations choosing each
kind of action, per lambda_A), all as PDF and PNG. Baseline policies of an earlier study
(`wp4b_results`, `joined`) are read on the run's worlds after a check of their seeds and
NoReaction makespans against the run's own NoReaction rows. Every run counts once. On-time
shares carry 95 % Wilson intervals over the runs of a cell (Wilson 1927). Paired differences
against each reference policy are taken over the runs of the same world (set, instance,
scenario, replication; common random numbers) and carry 95 % percentile intervals of a cluster
bootstrap over the instances of a set (Davison & Hinkley 1997); every policy has the same
worlds, so a paired difference of means equals the difference of the policies' means. To
regenerate the summaries of a run:

    uv run sentinel summarise-policies results/wp4/<run_id>
"""

import csv
import gzip
import hashlib
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO, get_args

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from sentinel.agent.candidates import KINDS
from sentinel.agent.decide import Reason
from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import natural_key
from sentinel.experiments.forecast_summary import (
    GIT_EXCLUDE,
    MANIFEST_FILE,
    SUMMARY_FILE,
    SUMMARY_MANIFEST_FILE,
    Estimate,
    SeedCheck,
)
from sentinel.experiments.policy_config import PolicyStudyConfig
from sentinel.experiments.runs import derive_seed, git_state, load_toml, utc_iso, write_json
from sentinel.experiments.simulation_config import Scenario, met_column
from sentinel.experiments.simulation_summary import wilson_interval
from sentinel.forecasting.metrics import (
    FloatArray,
    IntArray,
    cluster_resamples,
    percentile_interval,
    resampled_ratio,
)
from sentinel.policies.registry import COMPARED

RESULTS_FILE = "results.csv.gz"
WP2B_POLICY = "no_reaction"  # the policy of the WP2b worlds
REASONS: tuple[str, ...] = get_args(Reason)
REFERENCE_LABELS = {"opt": "optimum", "hrs": "best known", "lb": "lower bound"}
POLICY_LABELS = {
    "no_reaction": "NoReaction",
    "always_substitute": "AlwaysSubstitute",
    "full_resolve": "FullResolve",
    "full_resolve_subst": "FullResolve(subst)",
    "stable_resolve": "StableResolve",
    "stable_resolve_subst": "StableResolve(subst)",
    "sentinel_full": "Sentinel",
    "sentinel_no_ot": "Sentinel no OT",
    "sentinel_gate": "Sentinel Λ=2",
    "sentinel_scalarised": "Sentinel scalarised",
    "sentinel_lambda0": "Sentinel Λ=0",
    "sentinel_lambda1": "Sentinel Λ=1",
    "sentinel_descope": "Sentinel DESCOPE",
    "sentinel_delta03": "Sentinel δ=0.3",
}
# Chosen candidate kinds folded into the action groups of the actions figure (spec section 6).
ACTION_GROUPS = {
    "SHIFT": ("shift",),
    "RESEQ": ("reseq_m", "reseq_s"),
    "SUBST": ("subst", "subst_all", "subst_all_reseq_m"),
    "OVERTIME": ("ot_reseq_m",),
    "DESCOPE": ("descope",),
}
# Categorical slots of the dataviz reference palette (light) in their fixed order: a policy keeps
# the slot of its place in the registry in every figure; markers repeat the identity for print
# and colour-vision deficiencies. Text stays in ink colours.
_SLOT = {name: i for i, name in enumerate((*COMPARED, "stable_resolve"))}
_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
_INK, _INK_2, _MUTED, _GRID, _AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

CellKey = tuple[str, str | None, str]  # set, scenario (None: pooled over the run's), policy
World = tuple[str, str, str, int]  # set, instance, scenario, replication


@dataclass(frozen=True)
class PolicyRow:
    """The results fields the summaries use; `met` follows the config's deltas."""

    set_name: str
    instance: str
    scenario: str
    replication: int
    seed: int
    policy: str
    makespan: int
    ratio: float
    met: tuple[bool, ...]
    cost_ratio: float
    deviation: float
    nervousness: int
    substitutions: int
    onboarding_days: int
    handover_days: float
    reseqs: int
    fallbacks: int
    rejected: int
    epochs: int
    truncated: bool
    runtime_s: float
    total_cost: float = 0.0
    agent_delta: float | None = None
    shifts: int = 0
    hired: int = 0
    overtime_cost: float = 0.0
    descoped: int = 0
    scope_loss: float = 0.0
    deliberations: int = 0
    gate_exits: int = 0
    rollouts: int = 0
    deferrals: int = 0
    escalations: int = 0
    approvals_applied: int = 0
    approvals_discarded: int = 0
    deliberation_s: float = 0.0
    chosen: tuple[int, ...] = (0,) * len(KINDS)  # by candidate kind, KINDS order
    reasons: tuple[int, ...] = (0,) * len(REASONS)  # by reason, REASONS order

    @property
    def world(self) -> World:
        """The world of the run, shared by all policies (common random numbers)."""
        return (self.set_name, self.instance, self.scenario, self.replication)


@contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            yield handle
    else:
        with path.open(newline="", encoding="utf-8") as handle:
            yield handle


def read_results(path: Path, deltas: Sequence[float]) -> list[PolicyRow]:
    """Parse results.csv.gz (or a plain results.csv); the Sentinel columns of WP5b default to
    zero in files written before them (WP4b)."""

    def number(record: Mapping[str, str], key: str) -> float:
        value = record.get(key, "")
        return float(value) if value else 0.0

    with _open_text(path) as handle:
        return [
            PolicyRow(
                set_name=record["set"],
                instance=record["instance"],
                scenario=record["scenario"],
                replication=int(record["replication"]),
                seed=int(record["seed"]),
                policy=record["policy"],
                makespan=int(record["makespan"]),
                ratio=float(record["ratio_c_star"]),
                met=tuple(record[met_column(delta)] == "True" for delta in deltas),
                cost_ratio=float(record["cost_ratio"]),
                deviation=float(record["deviation"]),
                nervousness=int(record["nervousness"]),
                substitutions=int(record["substitutions"]),
                onboarding_days=int(record["onboarding_days"]),
                handover_days=float(record["handover_days"]),
                reseqs=int(record["reseqs"]),
                fallbacks=int(record["fallbacks"]),
                rejected=int(record["rejected"]),
                epochs=int(record["n_epochs"]),
                truncated=record["truncated"] == "True",
                runtime_s=float(record["runtime_s"]),
                total_cost=float(record["total_cost"]),
                agent_delta=float(record["agent_delta"]) if record.get("agent_delta") else None,
                shifts=int(number(record, "shifts")),
                hired=int(number(record, "hired")),
                overtime_cost=number(record, "overtime_cost"),
                descoped=int(number(record, "descoped")),
                scope_loss=number(record, "scope_loss"),
                deliberations=int(number(record, "deliberations")),
                gate_exits=int(number(record, "gate_exits")),
                rollouts=int(number(record, "rollouts")),
                deferrals=int(number(record, "deferrals")),
                escalations=int(number(record, "escalations")),
                approvals_applied=int(number(record, "approvals_applied")),
                approvals_discarded=int(number(record, "approvals_discarded")),
                deliberation_s=number(record, "deliberation_s"),
                chosen=tuple(int(number(record, f"chosen_{kind}")) for kind in KINDS),
                reasons=tuple(int(number(record, f"reason_{reason}")) for reason in REASONS),
            )
            for record in csv.DictReader(handle)
        ]


@dataclass(frozen=True)
class Cell:
    """Means per run of one cell (set, scenario or all scenarios, policy) and its counts."""

    n: int
    on_time: tuple[int, ...]  # runs on time, per delta_D
    ratio: float
    deviation: float
    nervousness: float
    substitutions: float
    onboarding_days: float
    handover_days: float
    cost_ratio: float
    reseqs: float
    epochs: float
    runtime_s: float
    fallbacks: int
    rejected: int
    truncated: int
    hired: float = 0.0
    overtime_share: float = 0.0  # overtime cost over total cost, summed over the runs
    descoped: float = 0.0
    scope_loss: float = 0.0
    deliberations: float = 0.0
    gate_exits: float = 0.0
    rollouts: float = 0.0  # per deliberation
    deliberation_s: float = 0.0  # per deliberation
    deferrals: float = 0.0
    escalations: float = 0.0
    approvals_applied: float = 0.0
    approvals_discarded: float = 0.0
    chosen: tuple[int, ...] = (0,) * len(KINDS)  # totals over the runs
    reasons: tuple[int, ...] = (0,) * len(REASONS)

    def share(self, i: int) -> float:
        """Share of runs on time for the i-th delta_D."""
        return self.on_time[i] / self.n

    def interval(self, i: int) -> tuple[float, float]:
        """95 % Wilson interval of the i-th on-time share."""
        return wilson_interval(self.on_time[i], self.n)

    @property
    def onboarding_per_substitution(self) -> float:
        """Mean onboarding days o_j per replaced member (NaN without substitutions)."""
        return self.onboarding_days / self.substitutions if self.substitutions else math.nan


def aggregate(rows: Sequence[PolicyRow], n_deltas: int) -> Cell:
    """The cell of a non-empty group of runs."""
    mean = np.mean
    deliberations = sum(r.deliberations for r in rows)
    cost = sum(r.total_cost for r in rows)
    return Cell(
        n=len(rows),
        on_time=tuple(sum(r.met[i] for r in rows) for i in range(n_deltas)),
        ratio=float(mean([r.ratio for r in rows])),
        deviation=float(mean([r.deviation for r in rows])),
        nervousness=float(mean([r.nervousness for r in rows])),
        substitutions=float(mean([r.substitutions for r in rows])),
        onboarding_days=float(mean([r.onboarding_days for r in rows])),
        handover_days=float(mean([r.handover_days for r in rows])),
        cost_ratio=float(mean([r.cost_ratio for r in rows])),
        reseqs=float(mean([r.reseqs for r in rows])),
        epochs=float(mean([r.epochs for r in rows])),
        runtime_s=float(mean([r.runtime_s for r in rows])),
        fallbacks=sum(r.fallbacks for r in rows),
        rejected=sum(r.rejected for r in rows),
        truncated=sum(r.truncated for r in rows),
        hired=float(mean([r.hired for r in rows])),
        overtime_share=sum(r.overtime_cost for r in rows) / cost if cost > 0 else 0.0,
        descoped=float(mean([r.descoped for r in rows])),
        scope_loss=float(mean([r.scope_loss for r in rows])),
        deliberations=deliberations / len(rows),
        gate_exits=float(mean([r.gate_exits for r in rows])),
        rollouts=sum(r.rollouts for r in rows) / deliberations if deliberations else 0.0,
        deliberation_s=(
            sum(r.deliberation_s for r in rows) / deliberations if deliberations else 0.0
        ),
        deferrals=float(mean([r.deferrals for r in rows])),
        escalations=float(mean([r.escalations for r in rows])),
        approvals_applied=float(mean([r.approvals_applied for r in rows])),
        approvals_discarded=float(mean([r.approvals_discarded for r in rows])),
        chosen=tuple(sum(r.chosen[i] for r in rows) for i in range(len(KINDS))),
        reasons=tuple(sum(r.reasons[i] for r in rows) for i in range(len(REASONS))),
    )


@dataclass(frozen=True)
class Difference:
    """Paired differences policy - reference over the same worlds: on time per delta_D in
    percentage points, C / C* and realised deviation in days, each with its interval."""

    n: int
    on_time: tuple[Estimate, ...]
    ratio: Estimate
    deviation: Estimate


class Analysis:
    """Cells and paired differences of a run (spec section 7.1).

    Cells exist per (set, scenario, policy) and pooled over the run's scenarios (scenario
    None); differences per cell and reference policy, for every reference with runs. Instance
    clusters are local to a set; each set has one resample matrix, seeded from (bootstrap_seed,
    "bootstrap", set) and shared by all statistics, so every difference uses the same
    resamples.
    """

    def __init__(self, rows: Sequence[PolicyRow], config: PolicyStudyConfig) -> None:
        settings = config.summary
        self.config = config
        present = {r.set_name for r in rows}
        self.sets = [s.name for s in config.sets if s.name in present]
        self.scenarios = [
            s for s in config.scenarios.expand() if any(r.scenario == s.name for r in rows)
        ]
        self.policies = list(config.analysed_policies)
        self.variants = [p for p in self.policies if p in config.sentinel_variants]
        self.reference = settings.reference_policy
        with_runs = {r.policy for r in rows}
        self.references = [p for p in settings.reference_policies if p in with_runs]
        unknown = with_runs - set(self.policies)
        if unknown:
            raise ValueError(f"results have policies missing from the config: {sorted(unknown)}")
        groups: dict[CellKey, list[PolicyRow]] = {}
        for row in rows:
            groups.setdefault((row.set_name, row.scenario, row.policy), []).append(row)
            groups.setdefault((row.set_name, None, row.policy), []).append(row)
        n_deltas = len(config.deltas)
        self.cells = {key: aggregate(group, n_deltas) for key, group in groups.items()}
        self.clusters: dict[str, dict[str, int]] = {}
        self.weights: dict[str, FloatArray] = {}
        for set_name in self.sets:
            names = sorted({r.instance for r in rows if r.set_name == set_name}, key=natural_key)
            self.clusters[set_name] = {name: c for c, name in enumerate(names)}
            rng = np.random.default_rng(derive_seed(settings.bootstrap_seed, "bootstrap", set_name))
            self.weights[set_name] = cluster_resamples(
                len(names), settings.bootstrap_resamples, rng
            )
        self.differences: dict[tuple[str, str | None, str, str], Difference] = {}
        for reference_policy in self.references:
            base = {row.world: row for row in rows if row.policy == reference_policy}
            for key, group in groups.items():
                if key[2] == reference_policy:
                    continue
                pairs = []
                for row in group:
                    reference = base.get(row.world)
                    if reference is None:
                        raise ValueError(
                            f"no {reference_policy} run for {row.policy} in {row.world}"
                        )
                    pairs.append((row, reference))
                difference = self._difference(key[0], pairs, n_deltas)
                self.differences[(*key, reference_policy)] = difference

    def _difference(
        self, set_name: str, pairs: Sequence[tuple[PolicyRow, PolicyRow]], n_deltas: int
    ) -> Difference:
        codes = np.array([self.clusters[set_name][row.instance] for row, _ in pairs], np.int64)
        on_time = tuple(
            self._mean(set_name, codes, [100.0 * (a.met[i] - b.met[i]) for a, b in pairs])
            for i in range(n_deltas)
        )
        return Difference(
            n=len(pairs),
            on_time=on_time,
            ratio=self._mean(set_name, codes, [a.ratio - b.ratio for a, b in pairs]),
            deviation=self._mean(set_name, codes, [a.deviation - b.deviation for a, b in pairs]),
        )

    def _mean(self, set_name: str, codes: IntArray, values: Sequence[float]) -> Estimate:
        """Mean of `values` (one per run, clusters `codes`) with its bootstrap interval."""
        weights = self.weights[set_name]
        size = weights.shape[1]
        total = np.bincount(codes, weights=np.asarray(values, dtype=np.float64), minlength=size)
        count = np.bincount(codes, minlength=size).astype(np.float64)
        value = float(total.sum() / count.sum()) if count.sum() else math.nan
        return Estimate(value, *percentile_interval(resampled_ratio(weights, total, count)))

    def cell(self, set_name: str, scenario: str | None, policy: str) -> Cell | None:
        return self.cells.get((set_name, scenario, policy))

    def difference(
        self, set_name: str, scenario: str | None, policy: str, reference: str | None = None
    ) -> Difference | None:
        """The paired difference against `reference` (default: the main reference policy)."""
        key = (set_name, scenario, policy, self.reference if reference is None else reference)
        return self.differences.get(key)


@dataclass(frozen=True)
class JoinCheck:
    """Baseline rows read from an earlier policy study for the run's worlds: the worlds of the
    run, the rows read, the seed mismatches over every row read, the NoReaction makespan
    mismatches against the run's own NoReaction rows, and the missing rows."""

    path: str
    policies: tuple[str, ...]
    worlds: int
    rows: int
    seed_mismatches: int
    makespan_mismatches: int
    missing: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "policies": list(self.policies),
            "worlds": self.worlds,
            "rows": self.rows,
            "seed_mismatches": self.seed_mismatches,
            "makespan_mismatches": self.makespan_mismatches,
            "missing": self.missing,
        }

    def line(self) -> str:
        return (
            f"- Baselines joined from `{self.path}`: {self.rows} rows of "
            + ", ".join(POLICY_LABELS.get(p, p) for p in self.policies)
            + f" on the run's {self.worlds} worlds, not rerun; **{self.makespan_mismatches} "
            f"NoReaction makespan mismatches** and {self.seed_mismatches} seed mismatches "
            f"against the run's own rows (expected 0), {self.missing} rows missing."
        )


def join_baselines(
    rows: Sequence[PolicyRow], config: PolicyStudyConfig
) -> tuple[list[PolicyRow], JoinCheck | None]:
    """The rows of the `joined` policies of `wp4b_results` on the run's worlds, and the check
    of that file's seeds (every row read) and NoReaction makespans against the run's rows."""
    path = config.wp4b_results
    if not config.joined or path is None:
        return [], None
    seeds = {row.world: row.seed for row in rows}
    own = {row.world: row.makespan for row in rows if row.policy == WP2B_POLICY}
    wanted = {*config.joined, WP2B_POLICY}
    theirs = [
        r for r in read_results(path, config.deltas) if r.world in seeds and r.policy in wanted
    ]
    joined = [r for r in theirs if r.policy in config.joined]
    noop = {r.world: r.makespan for r in theirs if r.policy == WP2B_POLICY}
    check = JoinCheck(
        path=path.as_posix(),
        policies=tuple(config.joined),
        worlds=len(seeds),
        rows=len(joined),
        seed_mismatches=sum(r.seed != seeds[r.world] for r in theirs),
        makespan_mismatches=sum(noop[w] != m for w, m in own.items() if w in noop),
        missing=len(seeds) * len(config.joined) - len(joined) + sum(w not in noop for w in own),
    )
    return joined, check


def wp2b_check(rows: Sequence[PolicyRow], path: Path | None) -> SeedCheck:
    """Compare every NoReaction run (one per world) with the WP2b row of the same world."""
    if path is None or not path.is_file():
        return SeedCheck(None if path is None else str(path), available=False)
    worlds = {row.world: (row.makespan, row.seed) for row in rows if row.policy == WP2B_POLICY}
    found: dict[World, tuple[int, int]] = {}
    with _open_text(path) as handle:
        for record in csv.DictReader(handle):
            key = (
                record["set"],
                record["instance"],
                record["scenario"],
                int(record["replication"]),
            )
            if key in worlds:
                found[key] = (int(record["makespan"]), int(record["seed"]))
    compared = [(worlds[key], found[key]) for key in worlds if key in found]
    return SeedCheck(
        str(path),
        available=True,
        checked=len(compared),
        makespan_mismatches=sum(ours[0] != theirs[0] for ours, theirs in compared),
        seed_mismatches=sum(ours[1] != theirs[1] for ours, theirs in compared),
        missing=len(worlds) - len(compared),
    )


# --- Markdown -------------------------------------------------------------------------------


def _num(value: float, digits: int = 3) -> str:
    if not math.isfinite(value):
        return "--"
    return f"{round(value, digits) + 0.0:.{digits}f}"  # + 0.0 turns -0.0 into 0.0


def _signed(value: float, digits: int) -> str:
    text = _num(value, digits)
    return text if text.startswith("-") or text == "--" or float(text) == 0 else "+" + text


def _est(estimate: Estimate, digits: int) -> str:
    return (
        f"{_signed(estimate.value, digits)} [{_num(estimate.low, digits)}, "
        f"{_num(estimate.high, digits)}]"
    )


def _share(cell: Cell, i: int) -> str:
    low, high = cell.interval(i)
    return f"{100 * cell.share(i):.1f} [{100 * low:.1f}, {100 * high:.1f}]"


def _provenance(git: Mapping[str, Any]) -> str:
    """The generating commit for the header, noting uncommitted changes outside results/."""
    if not git.get("commit"):
        return "outside a git checkout"
    dirty = " with uncommitted changes outside results/" if git.get("dirty") else ""
    return f"at commit `{git['commit']}`{dirty}"


def _scenario_cells(scenario: Scenario | None) -> str:
    if scenario is None:
        return "all | --"
    return f"{scenario.lambda_a:g} | {scenario.mean_absence:g}"


def summary_markdown(
    run_id: str,
    analysis: Analysis,
    seed_check: SeedCheck,
    rows: Sequence[PolicyRow],
    results_file: str,
    *,
    git: Mapping[str, Any],
    join: JoinCheck | None = None,
) -> str:
    """Human-readable tables per set: cells by lambda_A and pooled, paired differences against
    every reference policy and, for Sentinel variants, their counts, actions and reasons."""
    config = analysis.config
    settings = config.summary
    reference = " and ".join(POLICY_LABELS.get(p, p) for p in analysis.references)
    grid = config.scenarios
    strides = ", ".join(
        f"all of {s.name.upper()}" if s.stride == 1 else f"every {s.stride}th of {s.name.upper()}"
        for s in config.sets
    )
    stages = sum(r.reseqs * (2 if r.policy.startswith("stable") else 1) for r in rows)
    lines = [
        f"# {config.name}: run {run_id}",
        "",
        f"Generated from `{results_file}` by `sentinel.experiments.policy_summary` "
        f"{_provenance(git)}; do not edit.",
        "",
        f"- Policies on `{config.baseline}` baseline plans: "
        + ", ".join(POLICY_LABELS.get(p, p) for p in analysis.policies)
        + f". CP-SAT: T_cp = {config.deterministic_time_limit:g} deterministic s per stage, "
        f"seed {config.cp_seed}, one worker; T_r = {config.review_period}.",
        f"- Instances: {strides} in natural order; {config.replications} replications per "
        "instance with the WP2b seeds, shared by all policies and scenarios (common random "
        f"numbers). Scenarios: λ_S = {grid.lambda_s:g}, λ_N = {grid.lambda_n:g}.",
        "- On time for δ: C ≤ D = ceil((1 + δ) C*) (spec section 1.2), evaluated post hoc; "
        "truncated runs are late. In % with 95 % Wilson intervals over the runs of a cell, which "
        "understate the uncertainty across instances.",
        "- Deviation: realised deviation from the baseline plan in days; nervousness: changes of "
        "a planned start in the deviation set per run (spec section 7.1); substitutions: "
        "replaced crew members per run; onboarding: crew-member days o_j per replaced member; "
        f"cost / B with β = {config.beta:g}. Means per run.",
        f"- Paired differences against {reference} on the same worlds (set, instance, scenario, "
        "replication), means over the runs with 95 % percentile intervals of a cluster "
        f"bootstrap over the instances of a set ({settings.bootstrap_resamples} resamples, seed "
        f"{settings.bootstrap_seed}); on time in percentage points.",
        seed_check.line(),
        *([] if join is None else [join.line()]),
        *_variant_lines(config),
        f"- Checks: {sum(r.rejected for r in rows)} rejected operations, "
        f"{sum(r.fallbacks for r in rows)} CP-SAT fallbacks in {stages:,} stages, "
        f"{sum(r.truncated for r in rows)} truncated runs.",
    ]
    deltas = config.deltas
    on_time_headers = " | ".join(f"On time δ={d:g} [%]" for d in deltas)
    delta_headers = " | ".join(f"Δ on time δ={d:g} [pp]" for d in deltas)
    by_set = {s.name: s for s in config.sets}
    for set_name in analysis.sets:
        s = by_set[set_name]
        n_instances = len(analysis.clusters[set_name])
        lines += [
            "",
            f"## {set_name.upper()} (C*: {REFERENCE_LABELS[s.reference]}, `{s.reference}`), "
            f"{n_instances} instances",
            "",
            f"| λ_A | E[L] | Policy | Runs | {on_time_headers} | C / C* | Deviation [d] | "
            "Nervousness | Substitutions | Onboarding [d] / subst. | Handover [d] | Cost / B | "
            "RESEQs | Fallbacks | Epochs | s / run |",
            "| ---: | ---: | --- |" + " ---: |" * (12 + len(deltas)),
        ]
        for scenario in [*analysis.scenarios, None]:
            for policy in analysis.policies:
                cell = analysis.cell(set_name, None if scenario is None else scenario.name, policy)
                if cell is None:
                    continue
                shares = " | ".join(_share(cell, i) for i in range(len(deltas)))
                lines.append(
                    f"| {_scenario_cells(scenario)} | {POLICY_LABELS.get(policy, policy)} | "
                    f"{cell.n} | {shares} | {_num(cell.ratio)} | {_num(cell.deviation, 2)} | "
                    f"{_num(cell.nervousness, 1)} | {_num(cell.substitutions, 1)} | "
                    f"{_num(cell.onboarding_per_substitution, 2)} | "
                    f"{_num(cell.handover_days, 1)} | {_num(cell.cost_ratio)} | "
                    f"{_num(cell.reseqs, 1)} | {cell.fallbacks} | {_num(cell.epochs, 1)} | "
                    f"{_num(cell.runtime_s, 3)} |"
                )
        for reference_policy in analysis.references:
            label = POLICY_LABELS.get(reference_policy, reference_policy)
            lines += [
                "",
                f"Paired differences against {label}:",
                "",
                f"| λ_A | E[L] | Policy | Pairs | {delta_headers} | Δ C / C* | Δ deviation [d] |",
                "| ---: | ---: | --- | ---: |" + " ---: |" * (2 + len(deltas)),
            ]
            for scenario in [*analysis.scenarios, None]:
                for policy in analysis.policies:
                    name = None if scenario is None else scenario.name
                    difference = analysis.difference(set_name, name, policy, reference_policy)
                    if difference is None:
                        continue
                    shifts = " | ".join(_est(e, 1) for e in difference.on_time)
                    lines.append(
                        f"| {_scenario_cells(scenario)} | {POLICY_LABELS.get(policy, policy)} | "
                        f"{difference.n} | {shifts} | {_est(difference.ratio, 3)} | "
                        f"{_est(difference.deviation, 2)} |"
                    )
        if analysis.variants:
            lines += _sentinel_tables(analysis, set_name)
    return "\n".join(lines) + "\n"


def _variant_lines(config: PolicyStudyConfig) -> list[str]:
    """One line per Sentinel variant: its parameters that differ from spec section 8."""
    lines = []
    defaults = SentinelParams()
    for name, variant in config.sentinel_variants.items():
        params = variant.params
        changed = {
            key: value
            for key, value in params.model_dump().items()
            if value != getattr(defaults, key)
            and key not in ("deterministic_time_limit", "cp_seed")
        }
        own = ", ".join(f"{key} = {value}" for key, value in sorted(changed.items()))
        lines.append(
            f"- {POLICY_LABELS.get(name, name)} (`{name}`): Sentinel with Λ = {params.autonomy}, "
            f"rule {params.rule}, N₁ = {params.n_stage1}, N = {params.n_rollouts}, working "
            f"towards δ_D = {variant.delta_d:g}"
            + (f", φ = {variant.optional_share:g}" if variant.optional_share else "")
            + (f"; differs from spec section 8 in {own}" if own else "")
            + "."
        )
    return lines


def _sentinel_tables(analysis: Analysis, set_name: str) -> list[str]:
    """Per Sentinel variant and lambda_A: counts per run, chosen actions and the deciding
    components, the last two in % of deliberations."""
    groups = list(ACTION_GROUPS)
    deciding = [r for r in REASONS if r not in ("idle_events", "awaiting_approval", "approved")]
    lines = [
        "",
        "Sentinel per run: deliberations, needs-gate exits, rollouts and seconds per "
        "deliberation, temporary workers hired, overtime share of the cost, the permission "
        "gate's deferrals, escalations and approvals applied / discarded, scope loss:",
        "",
        "| λ_A | E[L] | Policy | Runs | Deliberations | Gate exits | Rollouts / del. | s / del. "
        "| Hired | Overtime share | Deferrals | Escalations | Applied | Discarded | Scope loss |",
        "| ---: | ---: | --- |" + " ---: |" * 12,
    ]
    for scenario in [*analysis.scenarios, None]:
        for policy in analysis.variants:
            cell = analysis.cell(set_name, None if scenario is None else scenario.name, policy)
            if cell is None:
                continue
            lines.append(
                f"| {_scenario_cells(scenario)} | {POLICY_LABELS.get(policy, policy)} | {cell.n} | "
                f"{_num(cell.deliberations, 1)} | {_num(cell.gate_exits, 1)} | "
                f"{_num(cell.rollouts, 0)} | {_num(cell.deliberation_s, 3)} | "
                f"{_num(cell.hired, 2)} | {_num(cell.overtime_share, 4)} | "
                f"{_num(cell.deferrals, 2)} | {_num(cell.escalations, 2)} | "
                f"{_num(cell.approvals_applied, 2)} | {_num(cell.approvals_discarded, 2)} | "
                f"{_num(cell.scope_loss, 3)} |"
            )
    lines += [
        "",
        "Chosen candidates (before the permission gate) and deciding components, % of "
        "deliberations; RESEQ: RESEQ-M and RESEQ-S, SUBST: SUBST(j), SUBST-ALL and "
        "SUBST-ALL+RESEQ-M, OVERTIME: OT+RESEQ-M:",
        "",
        "| λ_A | E[L] | Policy | Deliberations | Needs met | NOOP | "
        + " | ".join(groups)
        + " | "
        + " | ".join(deciding[1:])
        + " |",
        "| ---: | ---: | --- |" + " ---: |" * (3 + len(groups) + len(deciding) - 1),
    ]
    noop = KINDS.index("noop")
    for scenario in [*analysis.scenarios, None]:
        for policy in analysis.variants:
            cell = analysis.cell(set_name, None if scenario is None else scenario.name, policy)
            if cell is None or not cell.deliberations:
                continue
            total = cell.deliberations * cell.n
            exits = cell.reasons[REASONS.index("needs_met")]
            actions = [
                sum(cell.chosen[KINDS.index(kind)] for kind in ACTION_GROUPS[group])
                for group in groups
            ]
            reasons = [cell.reasons[REASONS.index(r)] for r in deciding[1:]]
            cells = [exits, cell.chosen[noop], *actions, *reasons]
            lines.append(
                f"| {_scenario_cells(scenario)} | {POLICY_LABELS.get(policy, policy)} | "
                f"{round(total)} | " + " | ".join(f"{100 * c / total:.1f}" for c in cells) + " |"
            )
    return lines


# --- LaTeX ----------------------------------------------------------------------------------

_TEX_LABELS = {
    "no_reaction": "NoReaction",
    "always_substitute": "AlwaysSubstitute",
    "full_resolve": "FullResolve",
    "full_resolve_subst": "FullResolve(S)",
    "stable_resolve": "StableResolve",
    "stable_resolve_subst": "StableResolve(S)",
    "sentinel_full": "Sentinel",
    "sentinel_no_ot": "Sentinel no OT",
    "sentinel_gate": r"Sentinel $\Lambda{=}2$",
    "sentinel_scalarised": "Sentinel scal.",
    "sentinel_lambda0": r"Sentinel $\Lambda{=}0$",
    "sentinel_lambda1": r"Sentinel $\Lambda{=}1$",
    "sentinel_descope": "Sentinel DESCOPE",
    "sentinel_delta03": r"Sentinel $\delta_D{=}0.3$",
}


def _tex_num(value: float, digits: int) -> str:
    """A number for LaTeX: a negative one gets a minus sign, `$-$0.4`, not a hyphen."""
    text = _num(value, digits)
    return "$-$" + text[1:] if text.startswith("-") and text != "--" else text


def _tex_ci(estimate: Estimate, digits: int, *, leading_zero: bool = True) -> str:
    """The interval in \\scriptsize, e.g. [0.8, 2.6] or, without leading zeros, [$-$.045, .012]."""
    parts = []
    for value in (estimate.low, estimate.high):
        text = _num(value, digits)
        if not leading_zero:
            text = text.replace("0.", ".", 1) if text.startswith(("0.", "-0.")) else text
        parts.append("$-$" + text[1:] if text.startswith("-") and text != "--" else text)
    return rf"{{\scriptsize[{parts[0]}, {parts[1]}]}}"


def latex_table(run_id: str, analysis: Analysis, reference_policy: str | None = None) -> str:
    """Booktabs tabular pooled per set and policy over the run's scenarios, at most nine columns:
    on time per delta_D, C / C*, deviation, nervousness, substitutions and cost / B; second rows
    hold the intervals of the paired differences against `reference_policy` (default: the
    main reference policy)."""
    config = analysis.config
    if reference_policy is None:
        reference_policy = analysis.reference
    deltas = config.deltas
    n_columns = 1 + len(deltas) + 5
    if n_columns > 9:
        raise ValueError(f"{len(deltas)} deadline slacks make {n_columns} columns; at most 9")
    scenarios = ", ".join(f"{s.lambda_a:g}" for s in analysis.scenarios)
    mean_absences = sorted({s.mean_absence for s in analysis.scenarios if s.mean_absence})
    reference = POLICY_LABELS.get(reference_policy, reference_policy)
    lines = [
        f"% Generated by sentinel.experiments.policy_summary from run {run_id}; do not edit.",
        f"% Means per run, pooled over lambda_A in {{{scenarios}}} (E[L] = "
        f"{', '.join(f'{m:g}' for m in mean_absences)}) and {config.replications} replications.",
        "% On time: C <= D = ceil((1 + delta_D) C*), in %. Deviation: realised deviation from the "
        "baseline plan in days; Nerv.: nervousness,",
        "% changes of a planned start per run (spec 7.1); Subst.: replaced crew members per run; "
        f"Cost/B with beta = {config.beta:g}. (S): with substitution.",
        f"% Second rows: 95 % cluster bootstrap intervals over instances of the paired difference "
        f"to {reference} (on time in pp),",
        "% equal to the difference of the means, since all policies run the same worlds. "
        r"Typeset with \small.",
        r"{\setlength{\tabcolsep}{3pt}%",
        rf"\begin{{tabular}}{{@{{}}l{'r' * (n_columns - 1)}@{{}}}}",
        r"\toprule",
        rf"Policy & \multicolumn{{{len(deltas)}}}{{c}}{{On time [\%]}} & $C/C^*$ & Deviation & "
        r"Nerv. & Subst. & Cost$/B$ \\",
        rf"\cmidrule(lr){{2-{1 + len(deltas)}}}",
        " & " + " & ".join(rf"$\delta_D = {d:g}$" for d in deltas) + r" & & [d] & & & \\",
    ]
    for set_name in analysis.sets:
        lines += [
            r"\midrule",
            rf"\multicolumn{{{n_columns}}}{{@{{}}l}}{{\textit{{{set_name.upper()}}}}} \\",
        ]
        for policy in analysis.policies:
            cell = analysis.cell(set_name, None, policy)
            if cell is None:
                continue
            shares = " & ".join(f"{100 * cell.share(i):.1f}" for i in range(len(deltas)))
            lines.append(
                f"{_TEX_LABELS.get(policy, policy)} & {shares} & {_tex_num(cell.ratio, 3)} & "
                f"{_tex_num(cell.deviation, 1)} & {_tex_num(cell.nervousness, 1)} & "
                f"{_tex_num(cell.substitutions, 1)} & {_tex_num(cell.cost_ratio, 3)} " + r"\\"
            )
            difference = analysis.difference(set_name, None, policy, reference_policy)
            if difference is not None:
                cis = " & ".join(_tex_ci(e, 1) for e in difference.on_time)
                lines.append(
                    f" & {cis} & {_tex_ci(difference.ratio, 3, leading_zero=False)} & "
                    f"{_tex_ci(difference.deviation, 1)} & & & " + r"\\"
                )
    lines += [r"\bottomrule", r"\end{tabular}}"]
    return "\n".join(lines) + "\n"


# --- Figures --------------------------------------------------------------------------------


def _style(ax: Axes) -> None:
    ax.grid(True, axis="both", color=_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", labelsize=7, colors=_INK_2, length=2.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_AXIS)


def _save(fig: Figure, path_stem: Path) -> list[str]:
    # Fixed metadata keeps repeated renders of the same results byte-identical.
    fig.savefig(path_stem.with_suffix(".pdf"), metadata={"CreationDate": None})
    fig.savefig(path_stem.with_suffix(".png"), dpi=200, metadata={"Software": None})
    return [f"{path_stem.name}.pdf", f"{path_stem.name}.png"]


def _color(policy: str) -> str:
    return _COLORS[_SLOT.get(policy, len(_SLOT)) % len(_COLORS)]


def _marker(policy: str) -> str:
    return _MARKERS[_SLOT.get(policy, len(_SLOT)) % len(_MARKERS)]


def ontime_figure(path_stem: Path, analysis: Analysis) -> list[str]:
    """On time against 100 lambda_A, one line per policy with 95 % Wilson error bars (dodged
    sideways so that they stay apart), a column of panels per set and a row per delta_D with a
    common y axis."""
    config = analysis.config
    deltas = config.deltas
    xs = [100 * s.lambda_a for s in analysis.scenarios]
    span = (max(xs) - min(xs)) or 1.0
    fig = Figure(figsize=(3.2 * len(analysis.sets), 2.3 * len(deltas)), layout="constrained")
    axes = fig.subplots(len(deltas), len(analysis.sets), squeeze=False, sharex=True, sharey="row")
    n = len(analysis.policies)
    tops = [0.0] * len(deltas)
    for col, set_name in enumerate(analysis.sets):
        for row, delta in enumerate(deltas):
            ax = axes[row][col]
            for k, policy in enumerate(analysis.policies):
                cells = [analysis.cell(set_name, s.name, policy) for s in analysis.scenarios]
                points = [(x, c) for x, c in zip(xs, cells, strict=True) if c is not None]
                if not points:
                    continue
                shift = (k - (n - 1) / 2) * 0.02 * span
                px = [x + shift for x, _ in points]
                py = [100 * c.share(row) for _, c in points]
                # Bar lengths; a Wilson bound at a share of 0 or 1 can miss it by rounding.
                low = [max(0.0, 100 * (c.share(row) - c.interval(row)[0])) for _, c in points]
                high = [max(0.0, 100 * (c.interval(row)[1] - c.share(row))) for _, c in points]
                tops[row] = max(tops[row], *(y + h for y, h in zip(py, high, strict=True)))
                ax.errorbar(
                    px,
                    py,
                    yerr=[low, high],
                    color=_color(policy),
                    marker=_marker(policy),
                    markersize=4,
                    linewidth=1.4,
                    elinewidth=0.8,
                    capsize=1.5,
                    clip_on=False,
                    label=POLICY_LABELS.get(policy, policy),
                )
            ax.set_xticks(xs, [f"{x:g}" for x in xs])
            ax.set_title(rf"{set_name.upper()}, $\delta_D = {delta:g}$", fontsize=9, color=_INK)
            if row == len(deltas) - 1:
                ax.set_xlabel(r"$\lambda_A$ [% per worker-day]", fontsize=8, color=_INK)
            if col == 0:
                ax.set_ylabel("On time [%]", fontsize=8, color=_INK)
            _style(ax)
    for row, top in enumerate(tops):
        axes[row][0].set_ylim(0, max(10.0, 10 * math.ceil(top / 10)))
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="outside upper center",
        ncols=min(len(labels), 3 if len(analysis.sets) > 1 else 2),  # one panel: narrower
        frameon=False,
        fontsize=7,
        labelcolor=_INK,
    )
    return _save(fig, path_stem)


def tradeoff_figure(path_stem: Path, analysis: Analysis) -> list[str]:
    """On time for the first delta_D against realised deviation, one point per policy and
    lambda_A connected in increasing lambda_A: a row of panels per set, one panel per policy,
    each with the reference policy's points in grey. One policy per panel keeps every panel to
    two series, which colour alone tells apart (at most three per scatter for the palette);
    the points of the panel's policy are labelled with 100 lambda_A."""
    others = [p for p in analysis.policies if p != analysis.reference]
    fig = Figure(
        figsize=(1.9 * max(1, len(others)), 2.1 * len(analysis.sets)), layout="constrained"
    )
    axes = fig.subplots(len(analysis.sets), max(1, len(others)), squeeze=False, sharey="row")
    reference = analysis.reference
    delta = analysis.config.deltas[0]
    for row, set_name in enumerate(analysis.sets):
        paths = {
            policy: [
                (cell.deviation, 100 * cell.share(0), 100 * s.lambda_a)
                for s in analysis.scenarios
                if (cell := analysis.cell(set_name, s.name, policy)) is not None
            ]
            for policy in analysis.policies
        }
        everything = [point for path in paths.values() for point in path]
        if not everything:
            continue
        left = min(p[0] for p in everything)
        right = max(p[0] for p in everything)
        pad = 0.08 * ((right - left) or 1.0)
        for col, policy in enumerate(others):
            ax = axes[row][col]
            for name, color, size, order in (
                (reference, _MUTED, 3.5, 2),
                (policy, _color(policy), 4.5, 3),
            ):
                path = paths[name]
                ax.plot(
                    [p[0] for p in path],
                    [p[1] for p in path],
                    color=color,
                    marker=_marker(name),
                    markersize=size,
                    linewidth=1.2,
                    zorder=order,
                    label=POLICY_LABELS.get(name, name),
                )
            for x, y, lam in paths[policy]:
                ax.annotate(
                    f"{lam:g}",
                    (x, y),
                    xytext=(3, 3),
                    textcoords="offset points",
                    fontsize=6,
                    color=_INK_2,
                )
            ax.set_xlim(left - pad, right + pad)
            ax.set_title(
                f"{set_name.upper()}: {POLICY_LABELS.get(policy, policy)}", fontsize=8, color=_INK
            )
            if row == len(analysis.sets) - 1:
                ax.set_xlabel("Realised deviation [d]", fontsize=7, color=_INK)
            if col == 0:
                ax.set_ylabel(rf"On time [%], $\delta_D = {delta:g}$", fontsize=7, color=_INK)
            _style(ax)
    legend = axes[0][0].legend(
        fontsize=6, frameon=False, loc="best", labelcolor=_INK, title=r"labels: $\lambda_A$ [%]"
    )
    legend.get_title().set_fontsize(6)
    legend.get_title().set_color(_INK_2)
    return _save(fig, path_stem)


def sentinel_tradeoff_figure(path_stem: Path, analysis: Analysis) -> list[str]:
    """On time for the first delta_D against realised deviation (top row) and against
    nervousness (bottom row), pooled over the run's scenarios: the Sentinel variants in the
    first categorical slots, direct-labelled, and the baselines as context in grey with one
    marker shape each (emphasis form). A scatter tells at most three hues apart, so the
    variants come in groups of at most three, a column of panels per set and group, each group
    with its own legend."""
    variants = analysis.variants
    groups = [variants[i : i + 3] for i in range(0, len(variants), 3)] or [[]]
    baselines = [p for p in analysis.policies if p not in variants]
    grey = {POLICY_LABELS.get(p, p) for p in baselines}
    delta = analysis.config.deltas[0]
    metrics = (
        ("deviation", "Realised deviation [d]"),
        ("nervousness", "Nervousness [changes / run]"),
    )
    columns = [(set_name, group) for set_name in analysis.sets for group in groups]
    fig = Figure(figsize=(3.3 * len(columns), 4.8), layout="constrained")
    axes = fig.subplots(len(metrics), len(columns), squeeze=False)
    shapes = ("s", "^", "D", "v", "P", "X")
    for col, (set_name, group) in enumerate(columns):
        for row, (metric, label) in enumerate(metrics):
            ax = axes[row][col]
            for k, policy in enumerate(baselines):
                cell = analysis.cell(set_name, None, policy)
                if cell is None:
                    continue
                ax.plot(
                    getattr(cell, metric),
                    100 * cell.share(0),
                    linestyle="none",
                    marker=shapes[k % len(shapes)],
                    markersize=4.5,
                    color=_MUTED,
                    zorder=2,
                    label=POLICY_LABELS.get(policy, policy),
                )
            for k, policy in enumerate(group):
                cell = analysis.cell(set_name, None, policy)
                if cell is None:
                    continue
                x, y = getattr(cell, metric), 100 * cell.share(0)
                ax.plot(
                    x,
                    y,
                    linestyle="none",
                    marker="o",
                    markersize=6,
                    markeredgecolor="white",
                    markeredgewidth=1.0,
                    color=_COLORS[k],
                    zorder=3,
                    label=POLICY_LABELS.get(policy, policy),
                )
                ax.annotate(
                    POLICY_LABELS.get(policy, policy),
                    (x, y),
                    xytext=(4, 3 - 7 * k),
                    textcoords="offset points",
                    fontsize=6,
                    color=_INK_2,
                )
            ax.set_xlabel(label, fontsize=7, color=_INK)
            if col == 0:
                ax.set_ylabel(rf"On time [%], $\delta_D = {delta:g}$", fontsize=7, color=_INK)
            if row == 0:
                ax.set_title(set_name.upper(), fontsize=9, color=_INK)
            _style(ax)
        if len(groups) > 1:
            own = [
                (h, text)
                for h, text in zip(*axes[0][col].get_legend_handles_labels(), strict=True)
                if text not in grey
            ]
            axes[0][col].legend(
                [h for h, _ in own],
                [text for _, text in own],
                fontsize=6,
                frameon=False,
                loc="best",
                labelcolor=_INK,
            )
    handles, labels = axes[0][0].get_legend_handles_labels()
    if len(groups) > 1:
        kept = [(h, text) for h, text in zip(handles, labels, strict=True) if text in grey]
        handles, labels = [h for h, _ in kept], [text for _, text in kept]
    fig.legend(
        handles,
        labels,
        loc="outside lower center",
        ncols=4,
        frameon=False,
        fontsize=6,
        labelcolor=_INK,
    )
    return _save(fig, path_stem)


def actions_figure(path_stem: Path, analysis: Analysis) -> list[str]:
    """Share of deliberations whose chosen candidate (before the permission gate) is an
    action, per lambda_A: stacked columns of the action groups in fixed categorical slots,
    the total on the cap; a row of panels per Sentinel variant and a column per set, with a
    common y axis. The rest of the deliberations kept NOOP or met the needs gate."""
    variants = analysis.variants
    groups = [
        group
        for group in ACTION_GROUPS
        if any(
            cell.chosen[KINDS.index(kind)]
            for key, cell in analysis.cells.items()
            if key[2] in variants
            for kind in ACTION_GROUPS[group]
        )
    ]
    slot = {group: i for i, group in enumerate(ACTION_GROUPS)}  # colour follows the group
    xs = list(range(len(analysis.scenarios)))
    fig = Figure(
        figsize=(2.6 * len(analysis.sets), 1.5 * len(variants) + 0.5), layout="constrained"
    )
    axes = fig.subplots(len(variants), len(analysis.sets), squeeze=False, sharex=True, sharey=True)
    top = 0.0
    for col, set_name in enumerate(analysis.sets):
        for row, policy in enumerate(variants):
            ax = axes[row][col]
            bottom = [0.0] * len(xs)
            totals = [0.0] * len(xs)
            for group in groups:
                heights = []
                for i, scenario in enumerate(analysis.scenarios):
                    cell = analysis.cell(set_name, scenario.name, policy)
                    total = 0.0 if cell is None else cell.deliberations * cell.n
                    count = (
                        0
                        if cell is None
                        else sum(cell.chosen[KINDS.index(kind)] for kind in ACTION_GROUPS[group])
                    )
                    heights.append(100 * count / total if total else 0.0)
                    totals[i] += heights[-1]
                ax.bar(
                    xs,
                    heights,
                    width=0.55,
                    bottom=bottom,
                    color=_COLORS[slot[group]],
                    edgecolor="white",
                    linewidth=0.8,
                    label=group,
                    zorder=2,
                )
                bottom = [b + h for b, h in zip(bottom, heights, strict=True)]
            for x, total in zip(xs, totals, strict=True):
                ax.annotate(
                    f"{total:.0f}",
                    (x, total),
                    xytext=(0, 2),
                    textcoords="offset points",
                    ha="center",
                    fontsize=6,
                    color=_INK_2,
                )
            top = max(top, *totals)
            ax.set_xticks(xs, [f"{100 * s.lambda_a:g}" for s in analysis.scenarios])
            if row == len(variants) - 1:
                ax.set_xlabel(r"$\lambda_A$ [% per worker-day]", fontsize=7, color=_INK)
            if col == 0:
                ax.set_ylabel("% of deliberations", fontsize=7, color=_INK)
            ax.set_title(
                f"{set_name.upper()}: {POLICY_LABELS.get(policy, policy)}", fontsize=8, color=_INK
            )
            _style(ax)
            ax.grid(False, axis="x")
    axes[0][0].set_ylim(0, max(10.0, 10 * math.ceil(1.15 * top / 10)))
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="outside upper center",
        ncols=len(labels),
        frameon=False,
        fontsize=7,
        labelcolor=_INK,
    )
    return _save(fig, path_stem)


# --- Entry points ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicySummaryOutputs:
    """Names of the generated files, the WP2b seed check and the check of the joined baselines
    (None without)."""

    files: list[str]
    seed_check: SeedCheck
    join_check: JoinCheck | None = None


def write_summaries(
    run_dir: Path,
    run_id: str,
    config: PolicyStudyConfig,
    results_file: str,
    *,
    read: Sequence[Path] = (),
    settings_source: str = "run config",
) -> PolicySummaryOutputs:
    """Generate summary.md, the LaTeX tables, the figures and summary_manifest.json from the
    run's results file and, if configured, the baselines of an earlier study. `read` lists the
    files read to obtain `config` and `settings_source` names the origin of its summary
    settings; both are recorded. Inputs are never written."""
    git = git_state(GIT_EXCLUDE)
    settings = config.summary
    results = run_dir / results_file
    rows = read_results(results, config.deltas)
    seed_check = wp2b_check(rows, config.wp2b_results)
    joined, join_check = join_baselines(rows, config)
    analysis = Analysis([*rows, *joined], config)
    texts = {
        SUMMARY_FILE: summary_markdown(
            run_id, analysis, seed_check, rows, results_file, git=git, join=join_check
        ),
        f"{settings.table}.tex": latex_table(run_id, analysis),
        **{
            f"{settings.table}_vs_{other}.tex": latex_table(run_id, analysis, other)
            for other in analysis.references[1:]
        },
    }
    for name, text in texts.items():
        (run_dir / name).write_text(text, encoding="utf-8")
    files = list(texts)
    prefix = run_dir / settings.figure_prefix
    if analysis.variants:
        files += sentinel_tradeoff_figure(prefix.with_name(f"{prefix.name}_tradeoff"), analysis)
        files += actions_figure(prefix.with_name(f"{prefix.name}_actions"), analysis)
    else:
        files += ontime_figure(prefix.with_name(f"{prefix.name}_ontime"), analysis)
        files += tradeoff_figure(prefix.with_name(f"{prefix.name}_tradeoff"), analysis)
    inputs = [results, *read]
    if seed_check.available and config.wp2b_results is not None:
        inputs.append(config.wp2b_results)
    if join_check is not None and config.wp4b_results is not None:
        inputs.append(config.wp4b_results)
    write_json(
        run_dir / SUMMARY_MANIFEST_FILE,
        {
            "run_id": run_id,
            "generator": "sentinel.experiments.policy_summary",
            "generated_utc": utc_iso(datetime.now(UTC)),
            "git_commit": git["commit"],
            "git_dirty": git["dirty"],
            "git_dirty_ignores": list(GIT_EXCLUDE),
            "summary_settings_source": settings_source,
            "summary_settings": settings.model_dump(mode="json"),
            "inputs": [_file_record(path, run_dir) for path in inputs],
            "wp2b_check": seed_check.as_dict(),
            "wp4b_check": None if join_check is None else join_check.as_dict(),
            "outputs": files,
        },
    )
    return PolicySummaryOutputs([*files, SUMMARY_MANIFEST_FILE], seed_check, join_check)


def _file_record(path: Path, run_dir: Path) -> dict[str, Any]:
    """An input file: its path (only its name inside the run directory), size and SHA-256."""
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    shown = path.name if path.parent == run_dir else path.as_posix()
    return {"path": shown, "bytes": path.stat().st_size, "sha256": digest}


def run_config(manifest: Mapping[str, Any]) -> tuple[PolicyStudyConfig, Path | None]:
    """The config of a run from its manifest. Its [summary] settings come from the config file
    the run was started with if that file still describes the same run (all other keys equal;
    ADR-0011); returns that file, or None if the manifest's own settings are used."""
    recorded: dict[str, Any] = manifest["config"]
    name = manifest.get("config_path")
    path = Path(name) if name else None
    if path is not None and path.is_file():
        current = load_toml(path)
        if _run_part(current) == _run_part(recorded):
            merged = {**recorded, "summary": current.get("summary", {})}
            return PolicyStudyConfig.model_validate(merged), path
    return PolicyStudyConfig.model_validate(recorded), None


def _run_part(config: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key != "summary"}


def regenerate(run_dir: Path) -> PolicySummaryOutputs:
    """Regenerate the summaries of an existing run directory from its manifest and results,
    with the summary settings of its config file if that file still describes the run."""
    manifest_path = run_dir / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config, source = run_config(manifest)
    return write_summaries(
        run_dir,
        manifest["run_id"],
        config,
        manifest["results_file"],
        read=[manifest_path, *([] if source is None else [source])],
        settings_source=MANIFEST_FILE if source is None else source.as_posix(),
    )
