"""Every verified quote of the evidence registry against the text of its fetched source (WP18).
Needs data/evidence from scripts/fetch_evidence.py; skips cleanly without it. A source that was
not fetched and a quote that is not in its fetched source fail as two separate tests (WP19)."""

import json
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from sentinel.evidence import load_registry, quote_occurs
from sentinel.evidence.load import ROOT
from sentinel.evidence.verify import source_readings

EVIDENCE = ROOT / "data" / "evidence"

pytestmark = pytest.mark.data


@pytest.fixture(scope="module")
def evidence_root() -> Path:
    """The fetched sources; skips the module cleanly if they were not fetched."""
    if not (EVIDENCE / "MANIFEST.json").is_file():
        pytest.skip("evidence sources not found in data/evidence; run scripts/fetch_evidence.py")
    return EVIDENCE


def quoted_sources() -> Iterator[tuple[str, str, str]]:
    """(item id, quote, source file) of every verified quote and official Polish wording."""
    for item in load_registry().items:
        check = item.verification
        if check.status != "verified" or item.kind == "own":
            continue
        for quote, name in ((item.quote, check.source_file), (item.quote_pl, check.source_file_pl)):
            if quote is not None and name is not None:
                yield item.id, quote, name


def test_every_quoted_source_was_fetched(evidence_root: Path) -> None:
    missing = [
        f"{ident}: {name}"
        for ident, _, name in quoted_sources()
        if not (evidence_root / "text" / f"{name}.txt").is_file()
    ]
    assert not missing, f"sources not fetched (run scripts/fetch_evidence.py): {missing}"


def test_every_verified_quote_occurs_in_its_fetched_source(evidence_root: Path) -> None:
    readings: dict[str, tuple[str, str]] = {}
    wrong = []
    checked = 0
    for ident, quote, name in quoted_sources():
        path = evidence_root / "text" / f"{name}.txt"
        if not path.is_file():
            continue  # reported by the test above
        if name not in readings:
            readings[name] = source_readings(path.read_text(encoding="utf-8"))
        checked += 1
        if not quote_occurs(quote, readings[name]):
            wrong.append(f"{ident}: {name}")
    assert not wrong, f"quotes not found in their fetched sources: {wrong}"
    assert checked >= 25


def test_the_fetched_sources_are_the_checked_ones(evidence_root: Path) -> None:
    """A source that changed upstream since the check is reported, not failed: its quotes are
    still checked against the new text above."""
    files = json.loads((evidence_root / "MANIFEST.json").read_text())["files"]
    changed = set()
    for item in load_registry().items:
        check = item.verification
        if check.status != "verified" or item.kind == "own":
            continue
        for name, digest in (
            (check.source_file, check.sha256),
            (check.source_file_pl, check.sha256_pl),
        ):
            fetched = files.get(name, {}).get("sha256") if name else None
            if fetched is not None and fetched != digest:
                changed.add(name)
    if changed:
        warnings.warn(f"sources changed since the check: {sorted(changed)}", stacklevel=1)
