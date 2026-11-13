"""Pydantic models of the evidence registry (docs/research/evidence/registry.json), the decision
catalogue (docs/research/decisions.md) and the boundary map (docs/research/boundary-map.json)."""

import re
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sentinel.evidence.verify import sentence_count

Module = Literal["raporty", "projekty", "finanse", "ludzie", "uprawnienia", "mapa"]
Stance = Literal["wspiera", "podwaza", "niuansuje"]
# empirical: a study with data; theoretical: theory, a review of ideas or a vision; law: a
# legal text; standard: a security, risk or accessibility standard; industry: a vendor's text;
# own: a result of Sentinel's own study (paper/generated/numbers.tex).
Kind = Literal["empirical", "theoretical", "law", "standard", "industry", "own"]
Zone = Literal["ai_samodzielnie", "ai_z_czlowiekiem", "tylko_czlowiek"]
Basis = Literal["empirical", "normative", "theoretical"]
MAX_QUOTE_SENTENCES = 3
NUMBERS_FILE = "paper/generated/numbers.tex"
SHA256 = re.compile(r"[0-9a-f]{64}")
ZONE_ORDER: dict[Zone, int] = {"ai_samodzielnie": 0, "ai_z_czlowiekiem": 1, "tylko_czlowiek": 2}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Source(_Frozen):
    """A fetched source: its file name under data/evidence/raw, where it comes from, how it is
    read, and the request headers it needs (the Official Journal by content negotiation). A
    `manual` source is not downloaded: the owner puts the file there (a paywalled article from
    the university library) and `url` says where to get it."""

    file: str = Field(pattern=r"^[a-z0-9_.-]+\.(pdf|html|xhtml|xml)$")
    url: str = Field(pattern=r"^https?://")
    format: Literal["pdf", "html", "xml"]
    title: str
    headers: dict[str, str] = Field(default_factory=dict)
    manual: bool = False
    note: str | None = None


class Figure(_Frozen):
    """A number of Sentinel's own study: a macro of paper/generated/numbers.tex and its value."""

    macro: str = Field(pattern=r"^[A-Za-z]+$")
    value: str
    label_pl: str


class Verification(_Frozen):
    """How an item was checked: `verified` quotes occur in the fetched source text (the file
    with this SHA-256) after the normalisation of `sentinel.evidence.verify`; `summary_only`
    items carry no quote and say why."""

    status: Literal["verified", "summary_only"]
    source_file: str | None = None
    sha256: str | None = None
    source_file_pl: str | None = None
    sha256_pl: str | None = None
    method: str
    checked_on: date | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        for digest in (self.sha256, self.sha256_pl):
            if digest is not None and not SHA256.fullmatch(digest):
                raise ValueError(f"not a SHA-256 digest: {digest}")
        if self.status == "verified":
            if self.source_file is None or self.sha256 is None or self.checked_on is None:
                raise ValueError("a verified item names its source file, its SHA-256 and a date")
            if self.reason is not None:
                raise ValueError("a verified item has no reason for being summary_only")
        elif not self.reason:
            raise ValueError("a summary_only item says why it has no quote")
        if (self.source_file_pl is None) != (self.sha256_pl is None):
            raise ValueError("the Polish source file and its SHA-256 come together")
        return self


class EvidenceItem(_Frozen):
    """One piece of evidence for or against design decisions (WP18, task 1)."""

    id: str = Field(pattern=r"^E\d{2}$")
    kind: Kind
    title_pl: str = Field(min_length=3, max_length=90)
    modules: list[Module]
    criteria: list[int]
    decisions: list[str]
    stance: Stance
    language: Literal["en", "pl"] = "en"
    quote: str | None = None
    quote_pl: str | None = None
    highlights: list[str] = Field(default_factory=list)
    highlights_pl: list[str] = Field(default_factory=list)
    gloss_pl: str | None = None
    location: str | None = None
    citation: str
    doi: str | None = None
    url: str | None = None
    open_access: bool
    licence: str | None = None
    summary_pl: str
    implication_pl: str
    verification: Verification
    figures: list[Figure] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    runs: int | None = None
    caveats_pl: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(set(self.modules)) != len(self.modules):
            raise ValueError(f"{self.id}: a module is listed twice")
        if any(c < 1 or c > 6 for c in self.criteria) or len(set(self.criteria)) != len(
            self.criteria
        ):
            raise ValueError(f"{self.id}: criteria are distinct numbers 1 to 6")
        if any(not re.fullmatch(r"D\d{2}", d) for d in self.decisions):
            raise ValueError(f"{self.id}: decision ids are D01, D02, ...")
        self._check_quotes()
        self._check_own()
        return self

    def _check_quotes(self) -> None:
        verified = self.verification.status == "verified"
        if not verified and (self.quote or self.quote_pl or self.highlights or self.gloss_pl):
            raise ValueError(f"{self.id}: a summary_only item has no quote, highlight or gloss")
        if self.quote_pl is not None and self.kind != "law":
            raise ValueError(f"{self.id}: only a legal text has an official Polish wording")
        if verified and self.kind != "own" and not (self.quote and self.gloss_pl and self.location):
            raise ValueError(f"{self.id}: a verified quote has a gloss and a location")
        if self.kind == "law" and verified and self.language == "en" and self.quote_pl is None:
            raise ValueError(f"{self.id}: a legal quote comes with its official Polish wording")
        if (self.quote_pl is not None) != (self.verification.source_file_pl is not None):
            raise ValueError(f"{self.id}: the Polish wording names its own source file")
        for text, marks in ((self.quote, self.highlights), (self.quote_pl, self.highlights_pl)):
            if text is None:
                continue
            if sentence_count(text) > MAX_QUOTE_SENTENCES:
                raise ValueError(f"{self.id}: a quote has at most {MAX_QUOTE_SENTENCES} sentences")
            for mark in marks:  # verbatim, so that the interface can mark it as it stands
                if not mark or mark not in text:
                    raise ValueError(f"{self.id}: highlight not in its quote: {mark!r}")

    def _check_own(self) -> None:
        if self.kind == "own":
            if not self.figures or not self.run_ids or self.runs is None or not self.caveats_pl:
                raise ValueError(f"{self.id}: own evidence has figures, run ids, runs, caveats")
            if self.quote is not None or self.verification.source_file != NUMBERS_FILE:
                raise ValueError(f"{self.id}: own evidence is checked against {NUMBERS_FILE}")
        elif self.figures or self.run_ids or self.runs is not None:
            raise ValueError(f"{self.id}: only own evidence has figures and runs")


class Registry(_Frozen):
    """The registry: its sources and items."""

    version: str
    normalisation: str
    sources: list[Source]
    items: list[EvidenceItem]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("an item id is used twice")
        files = {source.file for source in self.sources}
        if len(files) != len(self.sources):
            raise ValueError("a source file is listed twice")
        digests: dict[str, str] = {}
        for item in self.items:
            check = item.verification
            pairs = ((check.source_file, check.sha256), (check.source_file_pl, check.sha256_pl))
            for name, digest in pairs:
                if name is None or digest is None or item.kind == "own":
                    continue
                if name not in files:
                    raise ValueError(f"{item.id}: source file {name} is not in the sources")
                if digests.setdefault(name, digest) != digest:
                    raise ValueError(f"{item.id}: {name} has two different SHA-256 digests")
        return self

    def item(self, item_id: str) -> EvidenceItem:
        """The item with this id (KeyError if absent)."""
        for item in self.items:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def source(self, file: str) -> Source:
        """The source with this file name (KeyError if absent)."""
        for source in self.sources:
            if source.file == file:
                return source
        raise KeyError(file)


BASIS: dict[Kind, Basis] = {
    "empirical": "empirical",
    "own": "empirical",
    "law": "normative",
    "standard": "normative",
    "theoretical": "theoretical",
    "industry": "theoretical",
}


def basis(kinds: list[Kind]) -> Basis:
    """The strongest basis among a decision's evidence: a study with data, else a law or a
    standard, else theory (a vendor's text counts as no more than theory)."""
    found = {BASIS[kind] for kind in kinds}
    if "empirical" in found:
        return "empirical"
    if "normative" in found:
        return "normative"
    return "theoretical"


class Decision(_Frozen):
    """A design decision of the catalogue (docs/research/decisions.md)."""

    id: str = Field(pattern=r"^D\d{2}$")
    text: str
    screen: str
    evidence: list[str]
    status: Literal["current", "proposed"]
    basis: Basis


class Criterion(_Frozen):
    """A criterion of the boundary map (docs/research/boundary-criteria.md)."""

    id: int = Field(ge=1, le=6)
    name_pl: str
    definition_pl: str
    question_pl: str
    evidence: list[str]
    normative: bool


class BoundaryCell(_Frozen):
    """How one criterion places one process: a zone, the reason and its evidence."""

    criterion: int = Field(ge=1, le=6)
    zone: Zone
    reason_pl: str = Field(min_length=10)
    evidence: list[str] = Field(min_length=1)


class BoundaryProcess(_Frozen):
    """A company process of the survey with its cells; its zone is the strictest cell's."""

    id: str = Field(pattern=r"^P\d{2}$")
    name_pl: str
    zone: Zone
    reason_pl: str
    sentinel_pl: str
    cells: list[BoundaryCell]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if sorted(cell.criterion for cell in self.cells) != [1, 2, 3, 4, 5, 6]:
            raise ValueError(f"{self.id}: one cell per criterion 1 to 6")
        strictest = max((cell.zone for cell in self.cells), key=ZONE_ORDER.__getitem__)
        if self.zone != strictest:
            raise ValueError(f"{self.id}: the zone is the strictest cell's ({strictest})")
        return self


class BoundaryMap(_Frozen):
    """The boundary map: the six criteria and the twelve processes of the survey."""

    version: str
    zones: dict[Zone, str]
    criteria: list[Criterion]
    processes: list[BoundaryProcess]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if [c.id for c in self.criteria] != [1, 2, 3, 4, 5, 6]:
            raise ValueError("the map has the criteria 1 to 6 in order")
        ids = [p.id for p in self.processes]
        if len(set(ids)) != len(ids):
            raise ValueError("a process id is used twice")
        return self
