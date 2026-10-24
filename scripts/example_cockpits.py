"""Write the example cockpits of docs/dashboard/ (WP8): three worlds chosen by a deterministic
query over the committed WP5 results (the runs of `configs/paper.toml`), simulated again by the
cockpit with Polish labels, each checked against its WP5 row before it is written, and a README
listing them.

Usage: uv run python scripts/example_cockpits.py [--out docs/dashboard] [--lang pl]
"""

import argparse
import csv
import gzip
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sentinel.dashboard.assemble import Kpis
from sentinel.dashboard.cockpit import Cockpit, Options, build, save
from sentinel.dashboard.labels import LANGUAGES
from sentinel.dashboard.page import policy_name
from sentinel.data.psplib_loader import natural_key

PAPER_CONFIG = Path("configs/paper.toml")
_LANGUAGE_NAMES = {"en": "English", "pl": "Polish"}
LAMBDA_A = "0.01"  # the absence rate of the ablation and autonomy studies
Row = dict[str, str]
World = Mapping[str, Row]  # the rows of one world by policy


def _gap(world: World) -> int:
    return int(world["no_reaction"]["makespan"]) - int(world["sentinel_full"]["makespan"])


@dataclass(frozen=True)
class Example:
    """An example cockpit: the run (role in `configs/paper.toml`), the set, the policy and the
    rule that picks its world (`keep`, then the smallest `rank`, then instance and replication
    in natural order)."""

    name: str
    role: str
    set_name: str
    policy: str
    rule: str
    keep: Callable[[World], bool]
    rank: Callable[[World], tuple[float, ...]]


EXAMPLES = (
    Example(
        name="j30_sentinel_on_time",
        role="rq4_main",
        set_name="j30",
        policy="sentinel_full",
        rule="J30, lambda_A = 0.01: Sentinel meets D(0.2) and NoReaction does not; the largest "
        "makespan gap NoReaction - Sentinel",
        keep=lambda w: (
            w["sentinel_full"]["met_0.2"] == "True" and w["no_reaction"]["met_0.2"] == "False"
        ),
        rank=lambda w: (-_gap(w),),
    ),
    Example(
        name="j30_escalation",
        role="rq4_ablation",
        set_name="j30",
        policy="sentinel_gate",
        rule="J30, lambda_A = 0.01, Sentinel at autonomy 2: at least one escalation and one "
        "applied approval, D(0.2) met; the fewest deliberations",
        keep=lambda w: (
            int(w["sentinel_gate"]["escalations"]) >= 1
            and int(w["sentinel_gate"]["approvals_applied"]) >= 1
            and w["sentinel_gate"]["met_0.2"] == "True"
        ),
        rank=lambda w: (int(w["sentinel_gate"]["deliberations"]),),
    ),
    Example(
        name="j60_overtime",
        role="rq4_main",
        set_name="j60",
        policy="sentinel_full",
        rule="J60, lambda_A = 0.01: Sentinel hires temporary workers (OVERTIME) and meets D(0.2); "
        "the largest overtime cost",
        keep=lambda w: (
            int(w["sentinel_full"]["hired"]) >= 1 and w["sentinel_full"]["met_0.2"] == "True"
        ),
        rank=lambda w: (-float(w["sentinel_full"]["overtime_cost"]),),
    ),
)


def run_dir(role: str) -> Path:
    config = tomllib.loads(PAPER_CONFIG.read_text(encoding="utf-8"))
    return Path(config["runs"][role]["path"])


def worlds(run: Path, set_name: str) -> dict[tuple[str, str], dict[str, Row]]:
    """The rows of every world of a set at lambda_A = 0.01, by (instance, replication)."""
    found: dict[tuple[str, str], dict[str, Row]] = {}
    with gzip.open(run / "results.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["set"] == set_name and row["lambda_a"] == LAMBDA_A:
                found.setdefault((row["instance"], row["replication"]), {})[row["policy"]] = row
    return found


def choose(example: Example) -> tuple[str, int, World]:
    """The world of the example's rule: instance, replication and its rows."""
    candidates = [
        (key, world)
        for key, world in worlds(run_dir(example.role), example.set_name).items()
        if example.keep(world)
    ]
    if not candidates:
        raise SystemExit(f"{example.name}: no world matches the rule")
    (instance, replication), world = min(
        candidates,
        key=lambda item: (example.rank(item[1]), natural_key(item[0][0]), int(item[0][1])),
    )
    return instance, int(replication), world


def mismatches(cockpit: Cockpit, world: World) -> list[str]:
    """Differences between the cockpit's runs and the study rows of its world."""
    found = []
    for side in (cockpit.first, cockpit.second):
        row, k = world[side.run.name], side.kpis
        checks = [
            ("makespan", int(row["makespan"]), k.makespan),
            ("met_0.2", row["met_0.2"] == "True", k.on_time),
            ("hired", int(row["hired"]), k.hired),
            ("substitutions", int(row["substitutions"]), k.substituted),
        ]
        if k.deliberations is not None:
            checks += [
                ("deliberations", int(row["deliberations"]), k.deliberations),
                ("escalations", int(row["escalations"]), k.escalations),
                ("approvals_applied", int(row["approvals_applied"]), k.approvals),
            ]
        found += [
            f"{side.run.name} {name}: study {a}, cockpit {b}" for name, a, b in checks if a != b
        ]
    return found


def _count(n: int, word: str) -> str:
    """`n` and `word`, the word in the plural unless n is 1 (its last word gets an s)."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def describe(cockpit: Cockpit) -> str:
    """One sentence about what the cockpit shows (for the README and the WP report)."""
    world, a, b = cockpit.world, cockpit.first.kpis, cockpit.second.kpis
    name_a, name_b = policy_name(cockpit.first.run.name), policy_name(cockpit.second.run.name)

    def outcome(k: Kpis, name: str) -> str:
        verdict = "on time" if k.on_time else f"{_count(k.late_days, 'day')} late"
        return f"{name} finishes after {k.makespan} days ({verdict})"

    actions = []
    if a.plan_changes:
        moved = _count(a.moved, "planned start")
        actions.append(f"{_count(a.plan_changes, 'plan change')} moving {moved}")
    if a.hired:
        hired = _count(a.hired, "temporary worker")
        actions.append(f"{hired} (overtime cost {a.overtime_cost:.1f})")
    if a.substituted:
        actions.append(_count(a.substituted, "substituted crew member"))
    if a.escalations:
        deferrals = _count(a.deferrals or 0, "deferral")
        actions.append(
            f"{_count(a.escalations, 'escalation')} ({a.approvals} approved, {deferrals})"
        )
    return (
        f"{world.name}, replication {world.replication}, D = {world.deadline}: "
        f"{outcome(a, name_a)}, {outcome(b, name_b)}; {name_a} deliberates "
        f"{_count(a.deliberations or 0, 'time')} and uses "
        + ("; ".join(actions) or "no intervention")
        + "."
    )


def readme(entries: Sequence[tuple[Example, Path, Cockpit]], language: str) -> str:
    lines = [
        "# Example cockpits",
        "",
        "Generated by `uv run python scripts/example_cockpits.py` (WP8, ADR-0021); do not edit.",
        f"Each page is one self-contained HTML file with {_LANGUAGE_NAMES[language]} labels: "
        "open it in a browser, no network needed. The worlds are chosen by a "
        "deterministic query over the committed WP5 results (`configs/paper.toml`), simulated "
        "again with the same seeds and checked against their study rows (makespan, on time, "
        "hires, substitutions, deliberations, escalations, approvals).",
        "",
    ]
    for example, path, cockpit in entries:
        lines += [
            f"## [{path.name}]({path.name})",
            "",
            f"- Rule ({example.role}): {example.rule}.",
            f"- Shows: {describe(cockpit)}",
            f"- Command: `{cockpit.provenance.command}`",
            "",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("docs/dashboard"))
    parser.add_argument("--lang", choices=LANGUAGES, default="pl")
    args = parser.parse_args(argv)
    entries = []
    for example in EXAMPLES:
        instance, replication, world = choose(example)
        options = Options(
            set_name=example.set_name,
            instance=instance,
            replication=replication,
            lambda_a=float(LAMBDA_A),
            policy=example.policy,
            compare="no_reaction",
            language=args.lang,
        )
        path = args.out / f"{example.name}.html"
        cockpit = build(options, out=path)
        problems = mismatches(cockpit, world)
        if problems:
            print(f"{example.name}: the cockpit differs from its study row:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        save(cockpit, path)
        entries.append((example, path, cockpit))
        print(f"{path} ({path.stat().st_size / 1000:.0f} kB): {describe(cockpit)}", flush=True)
    (args.out / "README.md").write_text(readme(entries, args.lang), encoding="utf-8")
    print(args.out / "README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
