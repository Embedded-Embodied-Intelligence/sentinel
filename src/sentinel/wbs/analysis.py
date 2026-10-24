"""RQ1 error analysis (WP7): which true precedence edges extracted answers miss, by how the
description states them (`narrate.edge_phrasings`): on the successor's or the predecessor's
side, the number form of the stating block and the paragraph distance of the two activities.

The edges are those of edge recall (`score.score`): true edges whose two activities the answer
matches by name. The answers come from recorded sessions; the analysis calls no LLM.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from sentinel.wbs.extract import Extraction, Session, normalise_name
from sentinel.wbs.narrate import EdgePhrasing
from sentinel.wbs.score import match_activities, read_answer, stated_edges

DISTANCE_BINS: tuple[tuple[int, int | None], ...] = ((0, 0), (1, 2), (3, 5), (6, None))


@dataclass(frozen=True)
class EdgeOutcome:
    """A true edge between matched activities: its phrasing and whether the answer states it."""

    phrasing: EdgePhrasing
    found: bool


def edge_outcomes(
    answer: object, truth: Extraction, phrasings: Sequence[EdgePhrasing]
) -> tuple[EdgeOutcome, ...]:
    """The outcome of every true edge whose activities the parsed answer matches (None or any
    other non-object answer matches nothing)."""
    matched, _ = match_activities(read_answer(answer), truth)
    stated = stated_edges(matched)
    outcomes = []
    for phrasing in phrasings:
        edge = (normalise_name(phrasing.predecessor), normalise_name(phrasing.successor))
        if edge[0] in matched and edge[1] in matched:
            outcomes.append(EdgeOutcome(phrasing, edge in stated))
    return tuple(outcomes)


def answers_by_round(session: Session, rounds: int) -> tuple[object, ...]:
    """The parsed answer after each round 0..rounds; a session that ended earlier keeps its
    last answer (as in `rounds.csv`)."""
    last = len(session.rounds) - 1
    return tuple(session.rounds[min(r, last)].response.parsed for r in range(rounds + 1))


def distance_label(low: int, high: int | None) -> str:
    """A paragraph-distance bin as text: `0`, `1-2`, `6+`."""
    if high is None:
        return f"{low}+"
    return str(low) if low == high else f"{low}-{high}"


@dataclass(frozen=True)
class Rate:
    """Found edges out of a total; `value` is None for no edges."""

    found: int
    total: int

    @property
    def value(self) -> float | None:
        return self.found / self.total if self.total else None

    @property
    def missing(self) -> int:
        return self.total - self.found


@dataclass(frozen=True)
class ErrorCell:
    """The edge outcomes of a backend, style and round, pooled over its sessions; each outcome
    with the instance of its session (the cluster of a bootstrap)."""

    backend: str
    style: str
    round: int
    sessions: int
    outcomes: tuple[tuple[str, EdgeOutcome], ...]

    def rate(self, keep: Callable[[EdgePhrasing], bool] = lambda _: True) -> Rate:
        """Recall over the edges whose phrasing `keep` accepts."""
        kept = [o for _, o in self.outcomes if keep(o.phrasing)]
        return Rate(sum(o.found for o in kept), len(kept))

    def by_instance(self, keep: Callable[[EdgePhrasing], bool] = lambda _: True) -> dict[str, Rate]:
        """`rate` per instance, for every instance of the cell (Rate(0, 0) without such edges)."""
        result = {}
        for instance in dict.fromkeys(name for name, _ in self.outcomes):
            kept = [o for name, o in self.outcomes if name == instance and keep(o.phrasing)]
            result[instance] = Rate(sum(o.found for o in kept), len(kept))
        return result

    def side(self, side: str) -> Rate:
        return self.rate(lambda p: p.side == side)

    def numbers(self, form: str) -> Rate:
        return self.rate(lambda p: p.numbers == form)

    def distance(self, low: int, high: int | None, side: str | None = None) -> Rate:
        return self.rate(lambda p: in_bin(p, low, high) and side in (None, p.side))

    @property
    def missing_predecessor_share(self) -> float | None:
        """The share of the missed edges that are stated on the predecessor's side."""
        missing = self.rate().missing
        return self.side("predecessor").missing / missing if missing else None

    @property
    def predecessor_share(self) -> float | None:
        """The share of all edges stated on the predecessor's side (the base rate)."""
        return self.side("predecessor").total / len(self.outcomes) if self.outcomes else None


def in_bin(phrasing: EdgePhrasing, low: int, high: int | None) -> bool:
    """Whether the edge's paragraph distance lies in the bin [low, high] (None: unbounded)."""
    return phrasing.distance >= low and (high is None or phrasing.distance <= high)


def error_cells(
    sessions: Iterable[tuple[str, str, str, Sequence[tuple[EdgeOutcome, ...]]]],
) -> list[ErrorCell]:
    """Cells per (backend, style, round) in first-seen order from (instance, backend, style,
    outcomes by round) per session."""
    pooled: dict[tuple[str, str, int], list[tuple[str, EdgeOutcome]]] = {}
    counts: dict[tuple[str, str, int], int] = {}
    for instance, backend, style, by_round in sessions:
        for index, outcomes in enumerate(by_round):
            key = (backend, style, index)
            pooled.setdefault(key, []).extend((instance, o) for o in outcomes)
            counts[key] = counts.get(key, 0) + 1
    return [
        ErrorCell(backend, style, index, counts[(backend, style, index)], tuple(outcomes))
        for (backend, style, index), outcomes in pooled.items()
    ]
