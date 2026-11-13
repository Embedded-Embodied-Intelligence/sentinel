"""Loading the evidence registry, the decision catalogue and the boundary map from docs/research
(the repository's root is two levels above the package's src directory)."""

import json
import re
from pathlib import Path

from sentinel.evidence.model import BoundaryMap, Decision, Registry

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "docs" / "research"
REGISTRY_PATH = RESEARCH / "evidence" / "registry.json"
DECISIONS_PATH = RESEARCH / "decisions.md"
BOUNDARY_MAP_PATH = RESEARCH / "boundary-map.json"
DECISION_ROW = re.compile(r"^\|\s*(D\d{2})\s*\|")


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    """The evidence registry, validated."""
    return Registry.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_boundary_map(path: Path = BOUNDARY_MAP_PATH) -> BoundaryMap:
    """The boundary map of the twelve processes, validated."""
    return BoundaryMap.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_decisions(path: Path = DECISIONS_PATH) -> list[Decision]:
    """The decisions of the catalogue's table: | id | decision | screen | evidence | status |
    basis |, evidence ids separated by commas."""
    decisions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not DECISION_ROW.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            raise ValueError(f"a decision row has six cells: {line}")
        ident, text, screen, evidence, status, basis = cells
        decisions.append(
            Decision.model_validate(
                {
                    "id": ident,
                    "text": text,
                    "screen": screen,
                    "evidence": re.findall(r"E\d{2}", evidence),
                    "status": status,
                    "basis": basis,
                }
            )
        )
    return decisions
