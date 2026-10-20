"""Command line interface of the `sentinel` console script, e.g. `sentinel inspect j30/j301_1`."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sentinel.data.psplib_loader import DEFAULT_ROOT, FETCH_HINT, instance_path, load_psplib
from sentinel.data.reference import REFERENCE_KINDS, load_reference, reference_path
from sentinel.model.instance import ProjectInstance
from sentinel.scheduling.bounds import critical_path_lower_bound


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the requested command; returns the exit status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        return _inspect(parser, args)
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
