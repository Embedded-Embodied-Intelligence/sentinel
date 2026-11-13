"""The research layer of v3 (docs/design/v3-spec.md, sections 1 to 3; WP19): the "Dowód" point
at every feature and its panel (the decision, its basis and its evidence with verified quotes
only), Źródła (the whole registry) and Mapa granic (twelve processes, six criteria, three
zones). The data ship with the package (`sentinel.evidence`, ADR-0037); the texts we wrote come
in Polish and English, quotes never translated."""

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


def evidence_count(ident: str) -> int:
    """The number N of the point "ⓘ N" of a decision (0 for an unknown id)."""
    _, decisions, _ = research()
    return next((len(d.evidence) for d in decisions if d.id == ident), 0)


def cards_of(ids: Sequence[str], lang: str) -> list[Card]:
    registry, _, _ = research()
    return ordered(card(registry.item(i), lang) for i in ids)


@dataclass(frozen=True)
class Panel:
    """What the "Dowód" panel shows: a decision (its sentence and basis), or a cell of the map
    (the process, the criterion's question, the zone and the reason); then the evidence."""

    title: str
    lead: str
    basis: str | None
    zone: str | None
    question: str | None
    cards: list[Card]
    decision: str | None


def decision_panel(ident: str, lang: str) -> Panel:
    decision = decision_of(ident)
    text = decision.text_en if lang == "en" else decision.text_pl
    return Panel(
        title=ident,
        lead=text,
        basis=decision.basis,
        zone=None,
        question=None,
        cards=cards_of(decision.evidence, lang),
        decision=ident,
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
            survey=None,  # WP20: the survey's answers, when they exist
        )

    return routes
