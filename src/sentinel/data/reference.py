"""PSPLIB reference makespans: proven optima, best known upper bounds and lower bounds.

Solution files have a free-text header followed by data lines `Par Inst Value [extra ...]`
(see docs/notes/WP0.md). A data line is any line starting with three integers; the value may
carry a trailing `*` (LB = UB marker). A line starting with two integers that is not a valid
data line is an error, so that a format change can never drop entries silently.
"""

import re
from pathlib import Path
from typing import Literal

from sentinel.data.psplib_loader import DEFAULT_ROOT, FETCH_HINT

ReferenceKind = Literal["opt", "hrs", "lb"]
REFERENCE_KINDS: tuple[ReferenceKind, ...] = ("opt", "hrs", "lb")

_DATA_LINE = re.compile(r"\s*(\d+)\s+(\d+)\s+(\d+)\*?(?:\s|$)")
_STARTS_WITH_TWO_INTS = re.compile(r"\s*\d+\s+\d+(?:\s|$)")


def reference_path(set_name: str, kind: ReferenceKind, root: str | Path = DEFAULT_ROOT) -> Path:
    """Path of a solution file, `<root>/solutions/<set>_<kind>.sm`."""
    return Path(root) / "solutions" / f"{set_name}_{kind}.sm"


def parse_reference(text: str, set_name: str) -> dict[str, int]:
    """Parse solution-file text into values keyed `<set>/<set><Par>_<Inst>`, e.g. `j30/j301_1`."""
    values: dict[str, int] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = _DATA_LINE.match(line)
        if match is None:
            if _STARTS_WITH_TWO_INTS.match(line):
                raise ValueError(f"line {line_no}: malformed data line {line.strip()!r}")
            continue  # header, separator or blank line
        par, inst, value = (int(group) for group in match.groups())
        key = f"{set_name}/{set_name}{par}_{inst}"
        if key in values:
            raise ValueError(f"line {line_no}: duplicate entry for {key}")
        values[key] = value
    if not values:
        raise ValueError("no data lines found")
    return values


def load_reference(
    set_name: str, kind: ReferenceKind, root: str | Path = DEFAULT_ROOT
) -> dict[str, int]:
    """Reference makespans of one set and kind, e.g. `{"j30/j301_1": 43, ...}`."""
    path = reference_path(set_name, kind, root)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; {FETCH_HINT}")
    try:
        return parse_reference(path.read_text(encoding="utf-8", errors="replace"), set_name)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
