"""The research layer of v3 (docs/design/v3-spec.md, sections 1 to 3; WP19): the "Dowód" point
at every feature and its panel (the decision, its basis and its evidence with verified quotes
only), Źródła (the whole registry) and Mapa granic (twelve processes, six criteria, three
zones). The data ship with the package (`sentinel.evidence`, ADR-0037); the texts we wrote come
in Polish and English, quotes never translated."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from markupsafe import Markup, escape

from sentinel.app.errors import AppError
from sentinel.app.ui.core import Ui
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.evidence import (
    BoundaryCell,
    BoundaryProcess,
    Criterion,
    Decision,
    EvidenceItem,
    research,
)
from sentinel.evidence import survey as survey_data

STANCES = ("wspiera", "podwaza", "niuansuje")  # the panel's order (section 2)
KINDS = ("empirical", "theoretical", "law", "standard", "industry", "own")
MODULES = ("projekty", "raporty", "finanse", "ludzie", "uprawnienia", "mapa")
ZONES = ("ai_samodzielnie", "ai_z_czlowiekiem", "tylko_czlowiek")
TEXT_KINDS = ("law", "standard", "industry")  # "Co mówi ten tekst" instead of "Co zrobili badacze"
# Where a process of the map lives in Sentinel: a project's tab, or a screen of the group "Zasady
# AI" (Raporty and Finanse since WP20).
PROJECT_SCREENS = {"overview": "", "report": "/report", "decisions": "/decisions"}
SCREENS = {"people": "/people", "reports": "/reports", "finance": "/finance"}


@dataclass(frozen=True)
class Figure:
    label: str
    value: str


@dataclass(frozen=True)
class Card:
    """One evidence item as the panel and Źródła show it, in the page's language."""

    id: str
    stance: str
    kind: str
    tag: str | None  # "Nasze badanie (RQ4)"
    title: str
    quote: Markup | None  # verified only, the highlights in <mark>
    quote_lang: str
    gloss: str | None  # when the quote is not in the page's language
    summary: str
    implication: str
    citation: str
    link: str | None
    open_access: bool
    verified: bool
    figures: tuple[Figure, ...]
    caveats: str | None
    decisions: tuple[str, ...]
    modules: tuple[str, ...]
    criteria: tuple[int, ...]


def marked(text: str, highlights: Iterable[str]) -> Markup:
    """The quote, escaped, with every occurrence of its highlights in <mark> (verbatim, as the
    registry checks them; an overlap keeps the earlier one)."""
    spans: list[tuple[int, int]] = []
    for mark in highlights:
        start = text.find(mark)
        while mark and start >= 0:
            spans.append((start, start + len(mark)))
            start = text.find(mark, start + len(mark))
    out: list[str] = []
    at = 0
    for start, end in sorted(spans):
        if start < at:
            continue
        out += [str(escape(text[at:start])), "<mark>", str(escape(text[start:end])), "</mark>"]
        at = end
    out.append(str(escape(text[at:])))
    return Markup("".join(out))


def card(item: EvidenceItem, lang: str) -> Card:
    """An item in `lang`: a legal text's official wording in that language, any other quote in
    its own language with the gloss when that differs; never a quote that is not verified."""
    english = lang == "en"
    verified = item.verification.status == "verified"
    quote: Markup | None = None
    quote_lang = item.language
    if verified and item.quote is not None:
        if item.quote_pl is not None and not english:
            quote, quote_lang = marked(item.quote_pl, item.highlights_pl), "pl"
        else:
            quote = marked(item.quote, item.highlights)
    title = item.title_en if english else item.title_pl
    tag = None
    if item.kind == "own" and ": " in title:
        tag, title = title.split(": ", 1)
        title = title[:1].upper() + title[1:]
    gloss = item.gloss_en if english else item.gloss_pl
    caveats = item.caveats_en if english else item.caveats_pl
    link = f"https://doi.org/{item.doi}" if item.doi else item.url
    figures = tuple(Figure(f.label_en if english else f.label_pl, f.value) for f in item.figures)
    return Card(
        id=item.id,
        stance=item.stance,
        kind=item.kind,
        tag=tag,
        title=title,
        quote=quote,
        quote_lang=quote_lang,
        gloss=gloss if quote is not None and quote_lang != lang else None,
        summary=item.summary_en if english else item.summary_pl,
        implication=item.implication_en if english else item.implication_pl,
        citation=item.citation,
        link=link,
        open_access=item.open_access,
        verified=verified,
        figures=figures,
        caveats=caveats,
        decisions=tuple(item.decisions),
        modules=tuple(item.modules),
        criteria=tuple(item.criteria),
    )


def ordered(cards: Iterable[Card]) -> list[Card]:
    """Supporting, then challenging, then nuancing evidence; the registry's order within each."""
    return sorted(cards, key=lambda c: STANCES.index(c.stance))


def decision_of(ident: str) -> Decision:
    _, decisions, _ = research()
    for decision in decisions:
        if decision.id == ident:
            return decision
    raise AppError("not_found", "not_found")


def idents(ident: str) -> list[str]:
    """The decisions of a point: one id ("D14") or several merged into one point of a block
    ("D05+D24", WP21; a "+" in a query arrives as a space)."""
    return [part for part in re.split(r"[+,\s]+", ident) if part]


def evidence_of(ident: str) -> list[str]:
    """The evidence items of a point's decisions, each once, in the decisions' order."""
    _, decisions, _ = research()
    wanted = idents(ident)
    found: list[str] = []
    for decision in decisions:
        if decision.id in wanted:
            found += [e for e in decision.evidence if e not in found]
    return found


def evidence_count(ident: str) -> int:
    """The number N of the point "ⓘ N" of one or more decisions (0 for unknown ids)."""
    return len(evidence_of(ident))


def cards_of(ids: Sequence[str], lang: str) -> list[Card]:
    registry, _, _ = research()
    return ordered(card(registry.item(i), lang) for i in ids)


@dataclass(frozen=True)
class Line:
    """A decision as the panel lists it: its id, its sentence in the page's language, its basis."""

    id: str
    text: str
    basis: str


@dataclass(frozen=True)
class Panel:
    """What the "Dowód" panel shows: one or more decisions (each sentence and basis), or a cell
    of the map (the process, the criterion's question, the zone and the reason); then the
    evidence, short (WP21): a one-line count, then the first item of each stance, the rest one
    click away, so a challenging item is never hidden."""

    title: str
    lead: str
    basis: str | None
    zone: str | None
    question: str | None
    cards: list[Card]
    decision: str | None
    lines: tuple[Line, ...] = ()

    @property
    def counts(self) -> list[tuple[str, int]]:
        """The number of items of each stance present, in the panel's order."""
        found = [(s, sum(c.stance == s for c in self.cards)) for s in STANCES]
        return [(stance, n) for stance, n in found if n]

    @property
    def shown(self) -> list[Card]:
        """All items when there are at most three, else the first of each stance."""
        if len(self.cards) <= SHORT:
            return self.cards
        return [next(c for c in self.cards if c.stance == s) for s, _ in self.counts]

    @property
    def more(self) -> list[Card]:
        """The items behind "Pokaż wszystkie dowody", in the panel's order."""
        return [c for c in self.cards if c not in self.shown]


SHORT = 3  # a panel with more items shows the first of each stance (WP21)


def decision_panel(ident: str, lang: str) -> Panel:
    """The panel of one decision, or of the decisions of one block merged into one point."""
    wanted = idents(ident)
    found = [decision_of(i) for i in wanted]
    lines = tuple(Line(d.id, d.text_en if lang == "en" else d.text_pl, d.basis) for d in found)
    return Panel(
        title=" · ".join(wanted),
        lead=lines[0].text,
        basis=lines[0].basis,
        zone=None,
        question=None,
        cards=cards_of(evidence_of(ident), lang),
        decision=" · ".join(wanted),
        lines=lines,
    )


def find_cell(process_id: str, criterion: int) -> tuple[BoundaryProcess, Criterion, BoundaryCell]:
    _, _, boundary = research()
    for process in boundary.processes:
        if process.id == process_id:
            for cell in process.cells:
                if cell.criterion == criterion:
                    return process, boundary.criteria[criterion - 1], cell
    raise AppError("not_found", "not_found")


def cell_panel(process_id: str, criterion: int, lang: str) -> Panel:
    process, crit, cell = find_cell(process_id, criterion)
    english = lang == "en"
    return Panel(
        title=f"{process.name_en if english else process.name_pl} · "
        f"{crit.name_en if english else crit.name_pl}",
        lead=cell.reason_en if english else cell.reason_pl,
        basis=None,
        zone=cell.zone,
        question=crit.question_en if english else crit.question_pl,
        cards=cards_of(cell.evidence, lang),
        decision=None,
    )


def panel_of(request: Request) -> Panel | None:
    """The panel a deep link opens (`?dowod=D14`, or `?dowod=P05-2` for a cell of the map)."""
    wanted = request.query_params.get("dowod", "")
    lang = texts(request).lang
    try:
        if wanted.startswith("D"):
            return decision_panel(wanted, lang)
        if wanted.startswith("P") and "-" in wanted:
            process, _, number = wanted.partition("-")
            return cell_panel(process, int(number), lang)
    except (AppError, ValueError):
        return None
    return None


@dataclass(frozen=True)
class MapRow:
    process: BoundaryProcess
    name: str
    reason: str
    where: str
    href: str | None
    cells: list[tuple[BoundaryCell, str]]  # with the reason in the page's language


def map_rows(ui: Ui, request: Request, lang: str) -> list[MapRow]:
    """The twelve processes with where each lives in Sentinel (a link when the screen exists:
    a project's tab opens the first live project, Ludzie its own screen)."""
    _, _, boundary = research()
    english = lang == "en"
    first = next(
        (p.id for p in ui.services.projects(ui.session(request)) if p.kind == "live"), None
    )
    rows = []
    for process in boundary.processes:
        href = None
        if process.screen in PROJECT_SCREENS and first is not None:
            href = f"{PREFIX}/projects/{first}{PROJECT_SCREENS[process.screen]}"
        elif process.screen in SCREENS:
            href = PREFIX + SCREENS[process.screen]
        rows.append(
            MapRow(
                process=process,
                name=process.name_en if english else process.name_pl,
                reason=process.reason_en if english else process.reason_pl,
                where=process.sentinel_en if english else process.sentinel_pl,
                href=href,
                cells=[(c, c.reason_en if english else c.reason_pl) for c in process.cells],
            )
        )
    return rows


@dataclass(frozen=True)
class SurveyRow:
    """A process in the survey's view: the count and share of each answer, the answer given
    most often (None on a tie or without answers), the map's zone and whether they agree."""

    name: str
    counts: list[tuple[str, int, float]]
    total: int
    most: str | None
    ours: str
    agrees: bool


@dataclass(frozen=True)
class SurveyView:
    n: int
    shown: bool  # the survey's view is chosen (else only the switch)
    rows: list[SurveyRow]
    agreement: int
    weights: list[tuple[Criterion, float | None]]


def survey_view(boundary: Any, shown: bool, lang: str = "pl") -> SurveyView | None:
    """Mapa granic's survey view (v3 spec section 3), None before the survey is imported."""
    found = survey_data.load_survey(survey_data.SURVEY_PATH)
    if found is None:
        return None
    rows = []
    for process in boundary.processes:
        counts = found.processes.get(process.id, {})
        total = sum(counts.values())
        most = survey_data.majority(counts)
        shares = [
            (answer, counts.get(answer, 0), 100 * counts.get(answer, 0) / total if total else 0.0)
            for answer in survey_data.ANSWERS
        ]
        rows.append(
            SurveyRow(
                process.name_en if lang == "en" else process.name_pl,
                shares,
                total,
                most,
                process.zone,
                most == process.zone,
            )
        )
    weights = [
        (c, None if str(c.id) not in found.criteria else found.criteria[str(c.id)].mean)
        for c in boundary.criteria
    ]
    return SurveyView(found.n, shown, rows, survey_data.agreement(found, boundary), weights)


def sources_filter(request: Request, cards: list[Card]) -> tuple[list[Card], dict[str, str]]:
    """Źródła's filters from the query (module, criterion, stance, kind, words); without
    JavaScript the form submits them, with it the list filters as you type."""
    q = request.query_params
    chosen = {name: q.get(name, "") for name in ("module", "criterion", "stance", "kind", "q")}
    words = chosen["q"].strip().lower()
    shown = []
    for c in cards:
        if chosen["module"] and chosen["module"] not in c.modules:
            continue
        if chosen["criterion"] and chosen["criterion"] not in {str(n) for n in c.criteria}:
            continue
        if chosen["stance"] and c.stance != chosen["stance"]:
            continue
        if chosen["kind"] and c.kind != chosen["kind"]:
            continue
        if words and words not in " ".join((c.id, c.title, c.summary, c.citation)).lower():
            continue
        shown.append(c)
    return shown, chosen


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()

    @routes.get(PREFIX + "/dowod/{ident}")
    def dowod(request: Request, ident: str) -> Response:
        """The panel's content for a decision, fetched by the point."""
        return page(ui, request, "_dowod.html", panel=decision_panel(ident, texts(request).lang))

    @routes.get(PREFIX + "/dowod/cell/{process_id}/{criterion}")
    def dowod_cell(request: Request, process_id: str, criterion: int) -> Response:
        """The panel's content for a cell of Mapa granic."""
        lang = texts(request).lang
        return page(ui, request, "_dowod.html", panel=cell_panel(process_id, criterion, lang))

    @routes.get(PREFIX + "/sources")
    def sources(request: Request) -> Response:
        t = texts(request)
        registry, decisions, boundary = research()
        cards = [card(item, t.lang) for item in registry.items]
        shown, chosen = sources_filter(request, cards)
        values: dict[str, Any] = {
            "title": t("v2.src.title"),
            "nav": "sources",
            "cards": shown,
            "total": len(cards),
            "chosen": chosen,
            "modules": MODULES,
            "criteria": boundary.criteria,
            "stances": STANCES,
            "kinds": KINDS,
            "decision_ids": {d.id for d in decisions},
        }
        return page(ui, request, "sources.html", **values)

    @routes.get(PREFIX + "/map")
    def boundary_map(request: Request) -> Response:
        t = texts(request)
        _, _, boundary = research()
        return page(
            ui,
            request,
            "map.html",
            title=t("v2.map.title"),
            nav="map",
            criteria=boundary.criteria,
            rows=map_rows(ui, request, t.lang),
            zones=ZONES,
            full=request.query_params.get("view") == "all",  # every criterion (WP21)
            survey=survey_view(boundary, request.query_params.get("view") == "survey", t.lang),
        )

    return routes
