"""The evidence registry of v3 (WP18): sources for and against each design decision, with
verbatim quotes checked by code against the fetched source texts, the decision catalogue and the
boundary map; the data ship with the package (WP19, ADR-0037)."""

from sentinel.evidence.load import (
    BOUNDARY_MAP_PATH,
    DECISIONS_PATH,
    REGISTRY_PATH,
    load_boundary_map,
    load_decisions,
    load_registry,
    research,
)
from sentinel.evidence.model import (
    BoundaryCell,
    BoundaryMap,
    BoundaryProcess,
    Catalogue,
    Criterion,
    Decision,
    EvidenceItem,
    Figure,
    Registry,
    Source,
    Verification,
)
from sentinel.evidence.verify import normalise, quote_occurs, sentence_count

__all__ = [
    "BOUNDARY_MAP_PATH",
    "DECISIONS_PATH",
    "REGISTRY_PATH",
    "BoundaryCell",
    "BoundaryMap",
    "BoundaryProcess",
    "Catalogue",
    "Criterion",
    "Decision",
    "EvidenceItem",
    "Figure",
    "Registry",
    "Source",
    "Verification",
    "load_boundary_map",
    "load_decisions",
    "load_registry",
    "normalise",
    "quote_occurs",
    "research",
    "sentence_count",
]
