"""Paper artifacts (WP7): the macros file parses and defines every macro once, tables fit the
LNCS text width, the generator refuses a dirty, smoke, incomplete or tampered run, summary
cells parse; slow: the generator is deterministic and `reproduce --check` passes."""

import functools
import json
import re
import shutil
from pathlib import Path

import pytest
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.ft2font import FT2Font

from sentinel.experiments.paper import (
    DEFAULT_CONFIG,
    ENGLISH,
    POLISH_LANGUAGE,
    Macro,
    PaperConfig,
    RunRef,
    RunRefused,
    generate,
    numbers_tex,
    verify_run,
)
from sentinel.experiments.runs import load_toml
from sentinel.experiments.summary_tables import Parts, SummaryTables, TableError, parse_cell

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED = REPO_ROOT / "paper" / "generated"
NEWCOMMAND = re.compile(r"^\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$")
LIMIT_PT = 12.2 / 2.54 * 72.27  # the LNCS text width
SERIF = FT2Font(findfont(FontProperties(family="STIXGeneral")))
CM_FACTOR = 1.1  # Computer Modern runs wider than STIX (Times-like): a conservative margin


@pytest.fixture
def generated() -> Path:
    """The committed paper/generated/; skips cleanly before its first generation."""
    if not (GENERATED / "MANIFEST.json").is_file():
        pytest.skip("paper/generated/ not generated yet; run `uv run sentinel paper`")
    return GENERATED


def macros_of(path: Path) -> dict[str, str]:
    """Macro name -> value of a numbers.tex; every definition after a comment, braces balanced."""
    lines = path.read_text(encoding="utf-8").splitlines()
    found: dict[str, str] = {}
    for number, line in enumerate(lines):
        if not line.strip() or line.startswith("%"):
            continue
        match = NEWCOMMAND.match(line)
        assert match, f"{path}:{number + 1}: not a macro definition: {line}"
        name, value = match.groups()
        assert name not in found, f"{path}: \\{name} defined twice"
        assert lines[number - 1].startswith("% "), f"{path}: \\{name} has no source comment"
        depth = 0
        for char in value:
            depth += {"{": 1, "}": -1}.get(char, 0)
            assert depth >= 0, f"{path}: unbalanced braces in \\{name}"
        assert depth == 0, f"{path}: unbalanced braces in \\{name}"
        found[name] = value
    return found


def test_the_macro_files_parse_and_define_every_macro_once(generated: Path) -> None:
    english = macros_of(generated / "numbers.tex")
    polish = macros_of(generated / "pl" / "numbers.tex")
    assert list(english) == list(polish) and len(english) > 1000
    assert english["RQfourOnTimeSentinelJthirty"] == "37.1"
    assert polish["RQfourOnTimeSentinelJthirty"] == "37{,}1"
    assert english["RQfivePropVsRandomWinRateQwen"] == r"\ensuremath{-}6.7"
    assert english["MachineCores"] == "4"
    with pytest.raises(ValueError, match="twice"):
        numbers_tex([Macro("A", "1", "s"), Macro("A", "2", "s")], ENGLISH)
    with pytest.raises(ValueError, match="letters only"):
        numbers_tex([Macro("RQ4", "1", "s")], ENGLISH)


def test_numbers_are_written_with_proper_signs_and_the_decimal_mark() -> None:
    assert ENGLISH.number("-0.036") == r"\ensuremath{-}0.036"
    assert ENGLISH.number("+4.3") == r"\ensuremath{+}4.3"
    assert POLISH_LANGUAGE.number("-0.036") == r"\ensuremath{-}0{,}036"
    assert POLISH_LANGUAGE.interval("1.5", "2.5") == r"\tiny[1{,}5; 2{,}5]"
    assert ENGLISH.count(19200) == "19{,}200" and POLISH_LANGUAGE.count(19200) == r"19\,200"
    assert ENGLISH.label("On time [%]") == r"On time [\%]"
    assert POLISH_LANGUAGE.label("On time [%]") == r"Na czas [\%]"


def _plain(latex: str) -> str:
    minus, dash = chr(0x2212), chr(0x2013)  # minus sign, en dash
    for old, new in (
        (r"\ensuremath{-}", minus),
        (r"\ensuremath{+}", "+"),
        ("{,}", ","),
        (r"\%", "%"),
        (r"\,", " "),
        (r"$\Delta$", "Δ"),
        ("$C/C^*$", "C/C*"),
        ("$F_1$", "F1"),
        ("$-$", minus),
        ("--", dash),
    ):
        latex = latex.replace(old, new)
    return re.sub(r"[${}]", "", latex)


@functools.cache
def _advance(char: str, size: float) -> float:
    """The advance width in pt of a glyph at `size` pt (FreeType 16.16 units at 72 dpi)."""
    SERIF.set_size(size, 72)
    return float(SERIF.load_char(ord(char)).linearHoriAdvance) / 65536


def _width(text: str, size: float) -> float:
    return sum(_advance(char, size) for char in text) * CM_FACTOR


def _cell_width(cell: str) -> float:
    tiny = re.search(r"\\tiny(\[.*\])", cell)
    main = cell[: tiny.start()] if tiny else cell
    width = _width(_plain(main).strip() or " ", 9.0)
    if tiny:
        width += _width(" ", 9.0) + _width(_plain(tiny.group(1)), 5.0)
    return width


def table_width(path: Path) -> float:
    """Estimated width in pt of a generated tabular in \\small with tabcolsep 3 pt."""
    columns: list[float] = []
    spans: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.endswith(r"\\"):
            continue
        cells = [c.strip() for c in line[:-2].split("&")]
        if any(c.startswith(r"\multicolumn") for c in cells):
            stripped = [re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}", "", c) for c in cells]
            spans.append(max(_cell_width(c) for c in stripped))
            continue
        widths = [_cell_width(c) for c in cells]
        merged = [max(a, b) for a, b in zip(columns, widths, strict=False)]
        columns = merged + widths[len(columns) :]
    return max([sum(columns) + 6.0 * (len(columns) - 1), *spans])


@pytest.mark.parametrize("folder", ["", "pl"])
def test_the_tables_fit_the_lncs_text_width(generated: Path, folder: str) -> None:
    for number in range(1, 6):
        path = generated / folder / f"tab_rq{number}.tex"
        text = path.read_text(encoding="utf-8")
        assert r"\toprule" in text and r"\bottomrule" in text and r"\small" in text
        assert table_width(path) <= LIMIT_PT, f"{path}: {table_width(path):.0f} pt"


def _copy_run(tmp_path: Path, role: str) -> RunRef:
    config = PaperConfig.model_validate(load_toml(REPO_ROOT / DEFAULT_CONFIG))
    ref = config.runs[role]
    target = tmp_path / ref.path.name
    shutil.copytree(REPO_ROOT / ref.path, target)
    return RunRef(path=target, sha256=ref.sha256)


def test_the_generator_refuses_a_dirty_smoke_incomplete_or_tampered_run(tmp_path: Path) -> None:
    ref = _copy_run(tmp_path, "rq5_online")
    assert verify_run("rq5_online", ref).manifest["run_id"] == ref.path.name
    results = ref.path / "results.csv"
    original = results.read_bytes()
    results.write_bytes(original.replace(b",5,", b",6,", 1))
    with pytest.raises(RunRefused, match="differs from its pinned SHA-256"):
        verify_run("rq5_online", ref)
    results.write_bytes(original)
    manifest_path = ref.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for change, message in (
        ({"git_dirty": True}, "dirty tree"),
        ({"smoke": True}, "smoke run"),
        ({"status": "running"}, "status"),
    ):
        manifest_path.write_text(json.dumps({**manifest, **change}), encoding="utf-8")
        with pytest.raises(RunRefused, match=message):
            verify_run("rq5_online", ref)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RunRefused, match="differs"):  # the manifest itself is pinned
        verify_run("rq5_online", ref)
    unpinned = RunRef(path=ref.path, sha256={"manifest.json": ref.sha256["manifest.json"]})
    with pytest.raises(RunRefused, match="without a pinned hash"):
        verify_run("rq5_online", unpinned)
    manifest_path.unlink()
    with pytest.raises(RunRefused, match="missing"):
        verify_run("rq5_online", ref)


def test_summary_cells_parse_and_tables_are_found_by_section_caption_and_columns(
    tmp_path: Path,
) -> None:
    assert parse_cell("97.5 [87.1, 99.6] (n = 200)") == Parts("97.5", "87.1", "99.6", "200")
    assert parse_cell("4.6% [4.2, 5.1]") == Parts("4.6", "4.2", "5.1")
    assert parse_cell("+0.036 ± 0.021") == Parts("+0.036", se="0.021")
    assert parse_cell("240 (50.0%)") == Parts("240", share="50.0")
    assert parse_cell("150/150 (100 %)") == Parts("150", denominator="150", share="100")
    assert parse_cell("0.902 (765)") == Parts("0.902", n="765")
    with pytest.raises(ValueError):
        parse_cell("FEASIBLE 480")
    path = tmp_path / "summary.md"
    path.write_text(
        "# Run\n\n## J30 (C*: optimum)\n\n| Policy | On time | Runs |\n| --- | ---: | ---: |\n"
        "| A | 1.0 [0.5, 1.5] | 4 |\n| B | 2.0 [1.5, 2.5] | 4 |\n\nPaired differences:\n\n"
        "| Policy | Δ |\n| --- | ---: |\n| B | +1.0 [0.1, 1.9] |\n",
        encoding="utf-8",
    )
    tables = SummaryTables(path, "summary.md")
    main = tables.table("J30", columns=("Runs",))
    cell = main.cell("On time", Policy="B")
    assert (cell.text, cell.line) == ("2.0 [1.5, 2.5]", 8)
    assert cell.source(["Policy"]) == (
        'summary.md:8 | J30 (C*: optimum) | row Policy=B | column "On time"'
    )
    assert tables.table("J30", caption="Paired").cell("Δ", Policy="B").text == "+1.0 [0.1, 1.9]"
    with pytest.raises(TableError):
        tables.table("J30")  # two tables
    with pytest.raises(TableError):
        main.cell("On time", Policy="C")


def test_reproduce_commands_list_every_run_with_a_keyless_replay(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from sentinel.experiments.reproduce import commands

    config = PaperConfig.model_validate(load_toml(REPO_ROOT / DEFAULT_CONFIG))
    assert commands(REPO_ROOT / DEFAULT_CONFIG) == 0
    out = capsys.readouterr().out
    assert all(ref.path.as_posix() in out for ref in config.runs.values())
    assert out.count("uv run python -m sentinel.experiments.") == 14 + 5  # runs + replays
    assert "--cache-file results/wp6/20261023-215350-f5aad526/llm_cache.jsonl.gz" in out
    assert "9.2 h recorded" in out


@pytest.mark.slow
def test_the_generator_is_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    generate(REPO_ROOT / DEFAULT_CONFIG, first)
    generate(REPO_ROOT / DEFAULT_CONFIG, second)
    names = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
    assert len(names) == 26
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


@pytest.mark.slow
@pytest.mark.data
def test_reproduce_check_passes_on_the_repository(
    psplib_root: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every summary of the paper runs (the RQ1 error analysis narrates from data/psplib) and
    paper/generated/ regenerate byte for byte."""
    from sentinel.experiments.reproduce import check

    assert check(REPO_ROOT / DEFAULT_CONFIG) == 0, capsys.readouterr().out
