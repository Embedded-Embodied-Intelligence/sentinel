"""Loading the evidence registry, the decision catalogue and the boundary map, which ship with the
package in sentinel/evidence/data (wheel, release zip and Docker image; ADR-0037)."""

import json
from functools import cache
from pathlib import Path

from sentinel.evidence.model import BoundaryMap, Catalogue, Decision, Registry

ROOT = Path(__file__).resolve().parents[3]  # the repository, for the scripts and the tests
DATA = Path(__file__).resolve().parent / "data"
REGISTRY_PATH = DATA / "registry.json"
DECISIONS_PATH = DATA / "decisions.json"
BOUNDARY_MAP_PATH = DATA / "boundary-map.json"


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    """The evidence registry, validated."""
    return Registry.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_boundary_map(path: Path = BOUNDARY_MAP_PATH) -> BoundaryMap:
    """The boundary map of the twelve processes, validated."""
    return BoundaryMap.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_decisions(path: Path = DECISIONS_PATH) -> list[Decision]:
    """The decisions of the catalogue, validated."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(Catalogue.model_validate(data).decisions)


@cache
def research() -> tuple[Registry, list[Decision], BoundaryMap]:
    """The registry, the catalogue and the map the interface shows, loaded once per process."""
    return load_registry(), load_decisions(), load_boundary_map()
