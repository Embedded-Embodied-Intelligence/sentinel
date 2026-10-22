"""Command line interface of the `sentinel` console script, e.g. `sentinel inspect j30/j301_1`.

`sentinel baselines --set j30 --method cpsat_det` precomputes the cached baseline plans of a set
with the method parameters of a study config (default `configs/wp2_noreaction.toml`).
`sentinel summarise-forecasts results/wp3/<run_id>` regenerates the summaries of a forecast study,
`sentinel summarise-policies results/wp4/<run_id>` those of a policy study.
"""

import argparse
import multiprocessing
import statistics
import sys
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from pathlib import Path

from sentinel.data.psplib_loader import (
    DEFAULT_ROOT,
    FETCH_HINT,
    instance_path,
    list_instances,
    load_psplib,
)
from sentinel.data.reference import REFERENCE_KINDS, load_reference, reference_path
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.runs import load_toml
from sentinel.experiments.simulation_config import StudyConfig
from sentinel.model.instance import ProjectInstance
from sentinel.scheduling.bounds import critical_path_lower_bound
from sentinel.simulation.baselines import (
    BASELINE_NAMES,
    BaselineMethod,
    BaselinePlan,
    InvalidPlanError,
    cached_baseline,
)

DEFAULT_STUDY_CONFIG = Path("configs/wp2_noreaction.toml")
PROGRESS_INTERVAL_S = 10.0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the requested command; returns the exit status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        return _inspect(parser, args)
    if args.command == "baselines":
        return _baselines(parser, args)
    if args.command == "summarise-forecasts":
        return _summarise_forecasts(args)
    if args.command == "summarise-policies":
        return _summarise_policies(args)
    parser.error(f"unknown command {args.command!r}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentinel", description="Sentinel research prototype.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="summarise a PSPLIB instance")
    inspect.add_argument("instance", nargs="?", help="instance name <set>/<name>, e.g. j30/j301_1")
    inspect.add_argument("--file", type=Path, help="path to a PSPLIB .sm file instead of a name")
    inspect.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="PSPLIB data root (default: %(default)s)"
    )
    baselines = commands.add_parser(
        "baselines", help="precompute and cache the baseline plans of an instance set"
    )
    baselines.add_argument("--set", required=True, dest="set_name", help="instance set, e.g. j30")
    baselines.add_argument("--method", required=True, choices=BASELINE_NAMES)
    baselines.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_STUDY_CONFIG,
        help="study config with the method parameters (default: %(default)s)",
    )
    baselines.add_argument("--limit", type=int, help="only the first N instances of the set")
    baselines.add_argument("--workers", type=int, help="processes (default: the config's)")
    baselines.add_argument("--root", type=Path, help="PSPLIB data root (default: the config's)")
    baselines.add_argument("--cache", type=Path, help="cache root (default: the config's)")
    summarise = commands.add_parser(
        "summarise-forecasts", help="regenerate the summaries of a forecast study run"
    )
    summarise.add_argument("run_dir", type=Path, help="run directory with manifest.json")
    policies = commands.add_parser(
        "summarise-policies", help="regenerate the summaries of a policy study run"
    )
    policies.add_argument("run_dir", type=Path, help="run directory with manifest.json")
    return parser


def _inspect(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if (args.instance is None) == (args.file is None):
        parser.error("inspect: give either an instance name or --file")
    root: Path = args.root
    name: str | None = None
    if args.file is not None:
        path: Path = args.file
    else:
        name = args.instance
        set_name, _, stem = args.instance.partition("/")
        if not set_name or not stem:
            parser.error(f"inspect: expected <set>/<instance>, e.g. j30/j301_1, got {name!r}")
        path = instance_path(set_name, stem, root)
    if not path.is_file():
        hint = "" if args.file is not None else f"; {FETCH_HINT}"
        print(f"error: {path} not found{hint}", file=sys.stderr)
        return 1
    instance = load_psplib(path, name=name)
    for label, value in _summary(instance, path, root):
        print(f"{label + ':':<17}{value}")
    return 0


def _baselines(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.limit is not None and args.limit < 1:
        parser.error("baselines: --limit must be at least 1")
    if args.workers is not None and args.workers < 1:
        parser.error("baselines: --workers must be at least 1")
    if not args.config.is_file():
        print(f"error: config {args.config} not found", file=sys.stderr)
        return 1
    config = StudyConfig.model_validate(load_toml(args.config))
    method = config.baselines.method(args.method)
    root: Path = args.root or config.data_root
    cache: Path = args.cache or config.baseline_cache
    workers: int = args.workers or config.max_workers
    try:
        stems = list_instances(args.set_name, root)[: args.limit]
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{args.set_name} {method.kind}: {len(stems)} instances, {workers} workers -> {cache}")
    started = time.monotonic()
    try:
        results = _precompute(args.set_name, stems, method, root, cache, workers)
    except InvalidPlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - started
    plans = [plan for plan, _ in results]
    computed = [plan.runtime_s for plan, cached in results if not cached]
    statuses = ", ".join(f"{k} {v}" for k, v in sorted(Counter(p.status for p in plans).items()))
    print(
        f"done in {format_duration(elapsed)}: {len(computed)} computed, "
        f"{len(plans) - len(computed)} cached; statuses: {statuses or 'none'}"
    )
    if computed:
        print(
            f"computed plans: mean {statistics.fmean(computed):.2f} s, "
            f"max {max(computed):.2f} s per instance"
        )
    reference = next((s.reference for s in config.sets if s.name == args.set_name), None)
    if plans and reference is not None and reference_path(args.set_name, reference, root).is_file():
        c_star = load_reference(args.set_name, reference, root)
        ratios = [p.makespan / c_star[p.instance] for p in plans if p.instance in c_star]
        if ratios:
            at_c_star = sum(r == 1 for r in ratios)
            print(
                f"plan / C* ({reference}): mean {statistics.fmean(ratios):.4f}, "
                f"max {max(ratios):.4f}, at C* {at_c_star} of {len(ratios)}"
            )
    return 0


def _summarise_forecasts(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    if not (run_dir / "manifest.json").is_file():
        print(f"error: {run_dir / 'manifest.json'} not found", file=sys.stderr)
        return 1
    # Imported here so that the other commands do not load matplotlib.
    from sentinel.experiments.forecast_summary import regenerate

    outputs = regenerate(run_dir)
    for name in outputs.files:
        print(run_dir / name)
    print(outputs.seed_check.line().removeprefix("- "))
    if outputs.reference_check is not None:
        print(outputs.reference_check.line().removeprefix("- "))
    return 0


def _summarise_policies(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    if not (run_dir / "manifest.json").is_file():
        print(f"error: {run_dir / 'manifest.json'} not found", file=sys.stderr)
        return 1
    # Imported here so that the other commands do not load matplotlib.
    from sentinel.experiments.policy_summary import regenerate

    outputs = regenerate(run_dir)
    for name in outputs.files:
        print(run_dir / name)
    print(outputs.seed_check.line().removeprefix("- "))
    if outputs.join_check is not None:
        print(outputs.join_check.line().removeprefix("- "))
    return 0


def _baseline_task(
    set_name: str, stem: str, root: Path, method: BaselineMethod, cache: Path
) -> tuple[BaselinePlan, bool]:
    """Cached or newly computed baseline plan of one instance (in a worker process)."""
    return cached_baseline(load_psplib(instance_path(set_name, stem, root)), method, cache)


def _precompute(
    set_name: str,
    stems: Sequence[str],
    method: BaselineMethod,
    root: Path,
    cache: Path,
    workers: int,
) -> list[tuple[BaselinePlan, bool]]:
    """Baseline plans of `stems` (one process per instance task), with progress every ~10 s."""
    if workers == 1:
        return [_baseline_task(set_name, stem, root, method, cache) for stem in stems]
    results: list[tuple[BaselinePlan, bool]] = []
    started = last_report = time.monotonic()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures: list[Future[tuple[BaselinePlan, bool]]] = [
            pool.submit(_baseline_task, set_name, stem, root, method, cache) for stem in stems
        ]
        try:
            for future in as_completed(futures):
                results.append(future.result())
                now = time.monotonic()
                if now - last_report >= PROGRESS_INTERVAL_S and len(results) < len(stems):
                    elapsed = now - started
                    remaining = elapsed / len(results) * (len(stems) - len(results))
                    computed = sum(not cached for _, cached in results)
                    print(
                        f"[{format_duration(elapsed)}] {len(results)}/{len(stems)} instances "
                        f"({computed} computed), ~{format_duration(remaining)} remaining",
                        flush=True,
                    )
                    last_report = now
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return results


def _summary(instance: ProjectInstance, path: Path, root: Path) -> list[tuple[str, str]]:
    roles = ", ".join(f"{role.name}={role.capacity}" for role in instance.roles)
    references = _reference_makespans(instance.name, root)
    return [
        ("name", instance.name),
        ("file", str(path)),
        ("real activities", str(instance.n_real)),
        ("roles", f"{roles} ({len(instance.workers)} workers)"),
        ("total duration", str(sum(act.duration for act in instance.activities))),
        ("LB0", str(critical_path_lower_bound(instance))),
        ("reference", ", ".join(f"{k}={v}" for k, v in references.items()) or "none"),
    ]


def _reference_makespans(name: str, root: Path) -> dict[str, int]:
    """Reference makespans (opt, hrs, lb) listed for instance `<set>/<stem>` in solution files."""
    set_name = name.partition("/")[0]
    found: dict[str, int] = {}
    for kind in REFERENCE_KINDS:
        if reference_path(set_name, kind, root).is_file():
            value = load_reference(set_name, kind, root).get(name)
            if value is not None:
                found[kind] = value
    return found


if __name__ == "__main__":
    sys.exit(main())
