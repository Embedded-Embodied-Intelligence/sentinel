"""The evidence registry, the decision catalogue and the boundary map (WP18): their rules, their
coverage, how they point at each other, our own numbers against paper/generated/numbers.tex,
and the quote normalisation. The quotes against the fetched sources: test_evidence_sources.py."""

import hashlib
import re
import tomllib
from collections import Counter

import pytest
from pydantic import ValidationError

from sentinel.evidence import (
    EvidenceItem,
    Registry,
    load_boundary_map,
    load_decisions,
    load_registry,
    normalise,
    quote_occurs,
    sentence_count,
)
from sentinel.evidence.load import ROOT
from sentinel.evidence.model import NUMBERS_FILE, basis
from sentinel.evidence.text import markup_text

MODULES = ("raporty", "projekty", "finanse", "ludzie", "uprawnienia", "mapa")
MACRO = re.compile(r"^\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$")


@pytest.fixture(scope="module")
def registry() -> Registry:
    return load_registry()


def test_the_registry_covers_every_module_and_criterion(registry: Registry) -> None:
    items = registry.items
    assert len(items) >= 25
    for module in MODULES:
        assert sum(module in item.modules for item in items) >= 2, module
    for criterion in range(1, 7):
        assert sum(criterion in item.criteria for item in items) >= 2, criterion
    for module in ("raporty", "projekty", "mapa"):
        stances = {item.stance for item in items if module in item.modules}
        assert {"wspiera", "podwaza"} <= stances, module


def test_every_item_is_verified_or_says_why_not(registry: Registry) -> None:
    for item in registry.items:
        check = item.verification
        if check.status == "verified":
            assert item.quote or item.kind == "own", item.id
        else:
            assert check.reason and item.quote is None and not item.highlights, item.id
    statuses = Counter(item.verification.status for item in registry.items)
    assert statuses["verified"] > statuses["summary_only"]


def test_quotes_are_short_and_their_highlights_are_in_them(registry: Registry) -> None:
    for item in registry.items:
        for text, marks in ((item.quote, item.highlights), (item.quote_pl, item.highlights_pl)):
            if text is None:
                continue
            assert sentence_count(text) <= 3, item.id
            assert marks, f"{item.id}: a quote has at least one highlight"
            assert all(mark in text for mark in marks), item.id


def test_a_highlight_outside_its_quote_or_a_long_quote_is_refused(registry: Registry) -> None:
    data = registry.item("E06").model_dump()
    with pytest.raises(ValidationError, match="highlight not in its quote"):
        EvidenceItem.model_validate({**data, "highlights": ["not in the quote"]})
    long_quote = "One sentence here. Two sentences here. Three are here. Four is one too many."
    with pytest.raises(ValidationError, match="at most 3 sentences"):
        EvidenceItem.model_validate({**data, "quote": long_quote, "highlights": ["One"]})
    with pytest.raises(ValidationError, match="summary_only item has no quote"):
        EvidenceItem.model_validate(
            {**data, "verification": {"status": "summary_only", "method": "-", "reason": "x"}}
        )


def test_our_own_figures_are_the_paper_numbers(registry: Registry) -> None:
    numbers_path = ROOT / NUMBERS_FILE
    macros = {}
    for line in numbers_path.read_text(encoding="utf-8").splitlines():
        if match := MACRO.match(line):
            macros[match[1]] = (
                match[2].replace("\\ensuremath{+}", "+").replace("\\ensuremath{-}", "-")
            )
    digest = hashlib.sha256(numbers_path.read_bytes()).hexdigest()
    paper = tomllib.loads((ROOT / "configs" / "paper.toml").read_text(encoding="utf-8"))
    run_ids = {run["path"].rsplit("/", 1)[-1] for run in paper["runs"].values()}
    own = [item for item in registry.items if item.kind == "own"]
    assert len(own) >= 5
    for item in own:
        assert item.verification.sha256 == digest, f"{item.id}: numbers.tex changed"
        for figure in item.figures:
            assert macros.get(figure.macro) == figure.value, (item.id, figure.macro)
        assert set(item.run_ids) <= run_ids, item.id


def test_decisions_and_items_point_at_each_other(registry: Registry) -> None:
    decisions = load_decisions()
    ids = [decision.id for decision in decisions]
    assert ids == [f"D{n:02d}" for n in range(1, len(ids) + 1)]
    items = {item.id: item for item in registry.items}
    for decision in decisions:
        assert decision.evidence, decision.id
        for evidence in decision.evidence:
            assert decision.id in items[evidence].decisions, (decision.id, evidence)
        verified = [
            items[e].kind for e in decision.evidence if items[e].verification.status == "verified"
        ]
        assert decision.basis == basis(verified), decision.id
    for item in registry.items:
        for decision_id in item.decisions:
            assert decision_id in ids and item.id in decisions[ids.index(decision_id)].evidence
    assert [d.id for d in decisions if d.status == "proposed"] == ["D21"]


def test_every_cell_of_the_boundary_map_has_a_zone_reason_and_evidence(registry: Registry) -> None:
    boundary = load_boundary_map()
    items = {item.id: item for item in registry.items}
    assert len(boundary.processes) == 12
    for criterion in boundary.criteria:
        expected = sorted(i for i, item in items.items() if criterion.id in item.criteria)
        assert criterion.evidence == expected, criterion.id
        assert criterion.normative == (criterion.id == 5)
    for process in boundary.processes:
        for cell in process.cells:
            assert cell.zone and cell.reason_pl and cell.evidence
            assert set(cell.evidence) <= items.keys(), (process.id, cell.criterion)
    zones = Counter(process.zone for process in boundary.processes)
    assert set(zones) == {"ai_samodzielnie", "ai_z_czlowiekiem", "tylko_czlowiek"}


def test_the_normalisation_is_only_the_documented_one() -> None:
    source = "The \ufb01rst \u201cjagged\u201d fron-\ntier is human-\ncentric,\u00a0and   wide."
    assert quote_occurs('The first "jagged" frontier', source)
    assert quote_occurs("is human-centric, and wide.", source)
    assert quote_occurs("frontier is humancentric", source)
    assert not quote_occurs("the first", source)  # no case folding
    assert not quote_occurs("frontier is human centric", source)
    assert not quote_occurs("jagged frontier", source)  # punctuation stays
    assert normalise(" a\n\u2018b\u2019 ") == "a 'b'"


def test_sentences_are_counted_past_abbreviations() -> None:
    assert sentence_count("Art. 5 applies, e.g. to emotions. It is in force.") == 2
    assert sentence_count("One. Two? Three! Four.") == 4
    assert sentence_count("We label it \u2018judgment.\u2019 There is a risky action.") == 2


def test_page_text_keeps_noscript_and_drops_scripts() -> None:
    page = (
        "<html><head><title>t</title><script>var x;</script></head><body><p>One</p>"
        "<noscript><div>Two</div></noscript><template><p>Three</p></template>four</body></html>"
    )
    assert markup_text(page).split() == ["One", "Two", "four"]
