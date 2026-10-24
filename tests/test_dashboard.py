"""The project cockpit (WP8): one self-contained HTML page per simulated project. Generated on the
tiny fixture and a J30 world: it parses, has every section, links nowhere, stays under 2 MB and
is byte-identical for a fixed seed; template explanations use only record values; an LLM
explanation shows its faithfulness check; the J30 cockpit reproduces its WP5 row."""

import csv
import gzip
import json
import re
import shutil
from collections.abc import Sequence
from html.parser import HTMLParser
from pathlib import Path

import pytest

from sentinel import cli
from sentinel.dashboard.cockpit import (
    EXPLAIN_MODES,
    MAX_BYTES,
    Cockpit,
    Options,
    build,
    explained,
    save,
    write,
)
from sentinel.dashboard.explain import (
    LlmExplainer,
    checkable,
    explained_by_llm,
    template_explanation,
)
from sentinel.dashboard.labels import HOWTO, LANGUAGES, POLICY_NAMES, WORDS
from sentinel.dashboard.world import WP5_CONFIGS, Catalogue, CockpitError, load_catalogue
from sentinel.interpret.explain import check, render_record
from sentinel.llm import FakeLlmClient, Message

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ("kpis", "gantt", "risk", "log", "howto", "provenance")
MAIN_RUN = REPO_ROOT / "results" / "wp5" / "20261022-102609-e9d131b3" / "results.csv.gz"


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return load_catalogue(tuple(REPO_ROOT / path for path in WP5_CONFIGS))


@pytest.fixture(scope="module")
def tiny_root(tmp_path_factory: pytest.TempPathFactory, tiny_path: Path) -> Path:
    """A PSPLIB root with the tiny fixture as set `tiny` and its optimum 7."""
    root = tmp_path_factory.mktemp("data") / "psplib"
    (root / "tiny").mkdir(parents=True)
    (root / "solutions").mkdir()
    shutil.copy(tiny_path, root / "tiny" / "tiny1_1.sm")
    (root / "solutions" / "tiny_opt.sm").write_text(
        "Paramter Instance Makespan CPU-Time[sec.]\n1 1 7 0.0\n", encoding="utf-8"
    )
    return root


def tiny_options(root: Path, **changes: object) -> Options:
    """Sentinel at autonomy 2 against NoReaction on the tiny world with an escalation."""
    values: dict[str, object] = {
        "set_name": "tiny",
        "instance": "tiny1_1",
        "lambda_a": 0.1,
        "policy": "sentinel_gate",
        "root": root,
        "cache": root.parent / "baselines",
    }
    return Options(**(values | changes))  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def tiny_cockpit(
    tiny_root: Path, catalogue: Catalogue, tmp_path_factory: pytest.TempPathFactory
) -> Cockpit:
    out = tmp_path_factory.mktemp("cockpit") / "cockpit.html"
    return build(tiny_options(tiny_root), out=out, catalogue=catalogue)


class Structure(HTMLParser):
    """Checks that every element is closed in order and collects ids and URL attributes."""

    VOID = frozenset({"meta", "br", "input", "link", "img", "hr"})

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.ids: list[str] = []
        self.links: list[str] = []

    def _attributes(self, attrs: Sequence[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.append(value)
            if name in ("href", "src", "action", "xlink:href") and value:
                self.links.append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._attributes(attrs)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._attributes(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes {self.stack[-1:] or 'nothing'}")
        else:
            self.stack.pop()


def assert_page(path: Path) -> str:
    """The page parses with balanced elements, has every section, no URL and fits 2 MB."""
    data = path.read_bytes()
    assert len(data) <= MAX_BYTES
    text = data.decode("utf-8")
    parser = Structure()
    parser.feed(text)
    parser.close()
    assert parser.errors == [] and parser.stack == []
    assert set(SECTIONS) <= set(parser.ids)
    assert all(link.startswith("#") for link in parser.links)
    assert "http:" not in text and "https:" not in text and "//" not in text.replace("://", "")
    assert text.count("<svg") == text.count("</svg>") >= 3
    return text


def test_a_cockpit_on_the_tiny_instance_is_complete_offline_and_deterministic(
    tiny_root: Path, catalogue: Catalogue, tiny_cockpit: Cockpit, tmp_path: Path
) -> None:
    assert tiny_cockpit.out is not None
    text = assert_page(save(tiny_cockpit, tiny_cockpit.out))
    first = tiny_cockpit.out.read_bytes()
    write(tiny_options(tiny_root), tiny_cockpit.out, catalogue=catalogue)  # simulated again
    assert tiny_cockpit.out.read_bytes() == first  # same seed, same bytes
    log, records = tiny_cockpit.log, tiny_cockpit.first.run.records
    assert len(tiny_cockpit.explanations) == len(log)
    assert {"escalated", "approved"} <= {row.gate for row in log}
    assert [f.day for f in tiny_cockpit.forecasts] == [r.day for r in records if r.deliberated]
    for side in (tiny_cockpit.first, tiny_cockpit.second):
        assert f"{side.kpis.makespan} days" in text
    assert '<html lang="en">' in text and "Sentinel Λ=2" in text and "NoReaction" in text

    polish = save(explained(tiny_cockpit, None, "pl"), tmp_path / "kokpit.html")
    text_pl = assert_page(polish)
    assert '<html lang="pl">' in text_pl and "Kokpit Sentinel" in text_pl
    assert "Dziennik decyzji" in text_pl and "Decision log" not in text_pl
    assert "--lang pl" in text_pl


def test_template_explanations_use_only_values_of_the_decision_record(
    tiny_cockpit: Cockpit,
) -> None:
    """Spec section 10.4 applied to the templates: every cited fact equals the record, the
    chosen action and the deciding component are cited, and every number written in digits
    is a value of the rendered record, in English and in Polish."""
    checked = 0
    for row in tiny_cockpit.log:
        if row.record.needs is None:  # an approval day: only the approved label is written
            summary = template_explanation(row.record).summary
            assert row.record.chosen in summary and not re.search(r"\d+ %", summary)
            continue
        observation = tiny_cockpit.first.run.observations[row.day]
        rendered = render_record(row.record, observation, tiny_cockpit.first.run.params)
        for language in LANGUAGES:
            explanation = template_explanation(row.record, language)
            data = explanation.model_dump()
            data["summary"] = checkable(explanation.summary, language)
            result = check(data, row.record, rendered)
            assert result.fully_faithful, (row.day, language, explanation.summary)
            assert result.numbers > 0 and result.hallucinated == 0
            checked += 1
    assert checked >= 2


def _answer(faithful: bool) -> object:
    """A fake LLM answering from the rendered record: the chosen action and the deciding
    component, with a number the record does not show when not faithful."""

    def respond(messages: Sequence[Message]) -> str:
        text = messages[-1].content
        found = re.search(r'Chosen: "([^"]+)"\..*Deciding component: (\w+)\.', text)
        assert found is not None
        summary = "The agent keeps the deadline in view." if faithful else "Success at 99 %."
        facts = [
            {"kind": "chosen_action", "value": found[1]},
            {"kind": "deciding_component", "value": found[2]},
        ]
        return json.dumps({"summary": summary, "cited_facts": facts})

    return respond


@pytest.mark.parametrize("faithful", [True, False])
def test_llm_explanations_show_their_faithfulness_check(
    tiny_cockpit: Cockpit, tmp_path: Path, faithful: bool
) -> None:
    client = FakeLlmClient(_answer(faithful), model="fake-explainer")  # type: ignore[arg-type]
    config = REPO_ROOT / "configs" / "wp6_rq5_explanations.toml"
    cockpit = explained(tiny_cockpit, LlmExplainer("ollama", config_path=config, client=client))
    text = assert_page(save(cockpit, tmp_path / "llm.html"))
    pairs = zip(cockpit.log, cockpit.explanations, strict=True)
    by_llm = [shown for row, shown in pairs if explained_by_llm(row.record)]
    assert by_llm and all(shown.source == "llm" for shown in by_llm)
    assert len(client.requests) == len(by_llm) and "--explain ollama" in text
    if faithful:
        assert all(s.faithfulness and s.faithfulness.fully_faithful for s in by_llm)
        assert "faithful ✓" in text and "not faithful" not in text
    else:
        assert all(s.faithfulness and s.faithfulness.hallucinated == 1 for s in by_llm)
        assert "not faithful ✗" in text
    templates = [s for s in cockpit.explanations if s.source == "template"]
    assert len(templates) == len(cockpit.log) - len(by_llm)


def test_the_command_writes_a_cockpit_and_refuses_unknown_policies(
    tiny_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two baselines: no decision log, and forecasts every T_r days for the first."""
    monkeypatch.chdir(REPO_ROOT)  # the default configs are relative to the repository
    out = tmp_path / "cli.html"
    common = ["dashboard", "--set", "tiny", "--instance", "tiny1_1", "--root", str(tiny_root)]
    common += ["--cache", str(tiny_root.parent / "baselines"), "--lambda-a", "0.1"]
    command = [*common, "--policy", "no_reaction", "--compare", "full_resolve"]
    assert cli.main([*command, "--out", str(out)]) == 0
    text = assert_page(out)
    assert "does not deliberate" in text and "makes no forecast" in text
    assert "NoReaction: C =" in capsys.readouterr().out
    assert cli.main([*common, "--policy", "sentinel_unknown", "--out", str(out)]) == 1
    assert "unknown policy 'sentinel_unknown'" in capsys.readouterr().err
    assert cli.EXPLAIN_MODES == EXPLAIN_MODES and cli.LANGUAGES == LANGUAGES


def test_labels_cover_both_languages_and_the_summary_names(catalogue: Catalogue) -> None:
    from sentinel.experiments.policy_summary import POLICY_LABELS

    assert set(WORDS["en"]) == set(WORDS["pl"]) and len(HOWTO["en"]) == len(HOWTO["pl"])
    assert POLICY_NAMES == POLICY_LABELS
    assert set(catalogue.names) <= set(POLICY_NAMES)
    assert (
        catalogue.variant("sentinel_full") is not None and catalogue.variant("no_reaction") is None
    )
    with pytest.raises(CockpitError, match="unknown policy"):
        catalogue.variant("sentinel")


def _wp5_row(instance: str, lambda_a: str, replication: str, policy: str) -> dict[str, str]:
    with gzip.open(MAIN_RUN, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["set"], row["instance"], row["lambda_a"], row["replication"])
            if key == ("j30", instance, lambda_a, replication) and row["policy"] == policy:
                return row
    raise AssertionError(f"no WP5 row for {instance}, {policy}")


@pytest.mark.data
@pytest.mark.slow
def test_a_j30_cockpit_reproduces_its_wp5_row(
    psplib_root: Path, catalogue: Catalogue, tmp_path: Path
) -> None:
    del psplib_root  # the world config's data root
    options = Options(set_name="j30", instance="j301_1", lambda_a=0.01)
    out = tmp_path / "j30.html"
    _, cockpit = write(options, out, catalogue=catalogue)
    assert_page(out)
    assert_reproduces(cockpit)


def assert_reproduces(cockpit: Cockpit) -> None:
    """The cockpit's runs are the WP5 main run's rows of the same world."""
    world = cockpit.world
    for side in (cockpit.first, cockpit.second):
        row = _wp5_row(world.stem, str(world.lambda_a), str(world.replication), side.run.name)
        assert int(row["makespan"]) == side.kpis.makespan
        assert (row["met_0.2"] == "True") == side.kpis.on_time
        assert int(row["hired"]) == side.kpis.hired
        if side.kpis.deliberations is not None:
            assert int(row["deliberations"]) == side.kpis.deliberations
