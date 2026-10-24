"""Paper artifacts from the committed result runs (WP7, ADR-0020): `sentinel paper`.

Reads only the runs of `configs/paper.toml` and refuses one whose manifest is missing, not
completed, a smoke run or recorded with a dirty tree, or whose data files differ from the
SHA-256 pinned there (or from the inputs its summary manifest records). Every number comes from
a cell of a run's generated `summary.md`, as printed there (`summary_tables`), or, for the few
the summaries do not print, from the run's data files by the summaries' own code; nothing is
recomputed and no LLM is called. Writes, deterministically (same inputs and commit, same
bytes), to `paper/generated/` (English, LNCS) and `paper/generated/pl/` (Polish, decimal
commas):

- `numbers.tex`: one `\\newcommand` per cited number, each after a comment naming its source
  file, line, table, row and column;
- `tab_rq1.tex` ... `tab_rq5.tex`: booktabs tabulars for `\\small`, at most 12.2 cm wide;
- `fig_rq1.pdf` ... `fig_rq5.pdf` and `fig_rq4_autonomy.pdf` (`paper_figures`);
- English directory only: `numbers.md`, every macro with its value and source as a table for
  checking, and `MANIFEST.json`: generator commit, input runs and outputs with their SHA-256.

    uv run sentinel paper
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sentinel.experiments.runs import load_toml, summary_provenance, write_json
from sentinel.experiments.summary_tables import Parts, SummaryTables, Table, parse_cell

DEFAULT_CONFIG = Path("configs/paper.toml")
MANIFEST_NAME = "MANIFEST.json"
GIT_EXCLUDE = ("results", "paper/generated")  # generated outputs: no dirty code state
SUMMARY_FILES = ("summary.md", "summary_manifest.json")
ROLES = (
    "rq2",
    "calibration",
    "rq3",
    "rq3_misspec",
    "rq4_baselines",
    "rq4_sensitivity",
    "rq4_main",
    "rq4_ablation",
    "rq4_autonomy",
    "rq1",
    "rq5_events",
    "rq5_proposals",
    "rq5_explanations",
    "rq5_online",
)


class RunRef(BaseModel):
    """A result run and the SHA-256 of its manifest and raw output files."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: Path
    sha256: dict[str, str] = Field(min_length=1)


class PaperConfig(BaseModel):
    """The output directory and the runs the texts cite, by role."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    out_dir: Path
    runs: dict[str, RunRef]


class RunRefused(ValueError):
    """A run cannot serve the paper: missing, dirty, smoke, incomplete or tampered."""


@dataclass(frozen=True)
class Run:
    """A verified run: its role, directory, manifest and summary tables."""

    role: str
    path: Path
    manifest: Mapping[str, Any]
    tables: SummaryTables


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file's bytes."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def data_files(manifest: Mapping[str, Any]) -> list[str]:
    """The manifest and the raw outputs of a run: every output but summaries, tables, figures."""
    outputs = [str(name) for name in manifest.get("outputs", [])]
    raw = [
        name
        for name in outputs
        if name not in SUMMARY_FILES and not name.endswith((".tex", ".pdf", ".png"))
    ]
    return ["manifest.json", *raw]


def verify_run(role: str, ref: RunRef) -> Run:
    """The run of `ref` if it may serve the paper, else `RunRefused` saying why."""
    path = ref.path / "manifest.json"
    if not path.is_file():
        raise RunRefused(f"{role}: {path} is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise RunRefused(f"{role}: {ref.path} has status {manifest.get('status')!r}")
    if manifest.get("smoke"):
        raise RunRefused(f"{role}: {ref.path} is a smoke run")
    if manifest.get("git_dirty") is not False:
        raise RunRefused(
            f"{role}: {ref.path} was recorded with a dirty tree "
            f"(git_dirty: {manifest.get('git_dirty')})"
        )
    unpinned = sorted(set(data_files(manifest)) - set(ref.sha256))
    if unpinned:
        raise RunRefused(f"{role}: {ref.path} has data files without a pinned hash: {unpinned}")
    for name, expected in sorted(ref.sha256.items()):
        file = ref.path / name
        if not file.is_file():
            raise RunRefused(f"{role}: {file} is missing")
        if sha256_file(file) != expected:
            raise RunRefused(f"{role}: {file} differs from its pinned SHA-256 {expected[:12]}")
    summary_manifest = ref.path / "summary_manifest.json"
    if summary_manifest.is_file():
        recorded = json.loads(summary_manifest.read_text(encoding="utf-8"))
        for item in recorded.get("inputs", []):
            name = item.get("path")
            if name in ref.sha256 and item.get("sha256") != ref.sha256[name]:
                raise RunRefused(
                    f"{role}: the summaries of {ref.path} were made from another {name}"
                )
    summary = ref.path / "summary.md"
    if not summary.is_file():
        raise RunRefused(f"{role}: {summary} is missing")
    return Run(role, ref.path, manifest, SummaryTables(summary, summary.as_posix()))


def load_runs(config: PaperConfig) -> dict[str, Run]:
    """Every run of the config, verified."""
    missing = [role for role in ROLES if role not in config.runs]
    if missing:
        raise RunRefused(f"the paper config lacks the runs {missing}")
    return {role: verify_run(role, config.runs[role]) for role in ROLES}


# --- Numbers in LaTeX ---------------------------------------------------------------------


@dataclass(frozen=True)
class Language:
    """How numbers and labels are written: decimal mark, interval separator, labels."""

    code: str
    decimal: str
    separator: str
    thousands: str
    labels: Mapping[str, str] = field(default_factory=dict)

    def label(self, text: str) -> str:
        """The label in this language (English text is the key), percent signs escaped."""
        shown = self.labels.get(text, text) if self.code != "en" else text
        return re.sub(r"(?<!\\)%", r"\\%", shown)

    def number(self, text: str) -> str:
        """LaTeX for a printed number, safe in text and math mode: a proper minus or plus sign,
        the decimal mark of the language."""
        value = text.strip()
        sign = ""
        if value[:1] in "+-":
            sign = r"\ensuremath{-}" if value[0] == "-" else r"\ensuremath{+}"
            value = value[1:]
        return sign + value.replace(".", self.decimal)

    def count(self, value: int) -> str:
        """An integer with thousands separators from 10,000 on."""
        text = f"{value:,}" if abs(value) >= 10_000 else str(value)
        return text.replace(",", self.thousands)

    def interval(self, low: str, high: str) -> str:
        """A bracketed interval in `\\tiny`."""
        return rf"\tiny[{self.number(low)}{self.separator}{self.number(high)}]"


ENGLISH = Language("en", ".", ", ", "{,}")


# --- Macros -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Macro:
    """A cited value: macro name, value as printed, source; `text` values are not numbers."""

    name: str
    value: str
    source: str
    text: bool = False

    def latex(self, language: Language) -> str:
        if self.text:
            return _escape(self.value)
        if re.fullmatch(r"\d{5,}", self.value):
            return language.count(int(self.value))
        return language.number(self.value)


_NAME = re.compile(r"[A-Za-z]+")


def numbers_tex(macros: Sequence[Macro], language: Language) -> str:
    """`numbers.tex`: one comment and `\\newcommand` per macro."""
    names = [m.name for m in macros]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"macros defined twice: {duplicates}")
    bad = [n for n in names if not _NAME.fullmatch(n)]
    if bad:
        raise ValueError(f"macro names must be letters only: {bad}")
    lines = [
        "% Generated by sentinel.experiments.paper from configs/paper.toml; do not edit.",
        "% Every value as printed in its source; comments: file:line | table | row | column.",
        "",
    ]
    for macro in macros:
        lines += [f"% {macro.source}", rf"\newcommand{{\{macro.name}}}{{{macro.latex(language)}}}"]
    return "\n".join(lines) + "\n"


class Catalog:
    """Collects macros from summary cells; a name may be added once."""

    def __init__(self) -> None:
        self.macros: list[Macro] = []

    def cell(
        self,
        name: str,
        table: Table,
        column: str,
        key: Mapping[str, str],
        *,
        ci: bool = False,
        part: str = "value",
    ) -> Parts:
        """Add `name` (the cell's part) and, with `ci`, `nameLo` and `nameHi`."""
        cell = table.cell(column, **key)
        parts = parse_cell(cell.text)
        value = getattr(parts, part)
        if value is None:
            raise ValueError(f"{cell.source(list(key))}: no {part} in {cell.text!r}")
        source = cell.source(list(key))
        self.add(name, value, source + ("" if part == "value" else f" ({part})"))
        if ci:
            if parts.low is None or parts.high is None:
                raise ValueError(f"{source}: no interval in {cell.text!r}")
            self.add(name + "Lo", parts.low, source + " (interval, low)")
            self.add(name + "Hi", parts.high, source + " (interval, high)")
        return parts

    def add(self, name: str, value: str, source: str, *, text: bool = False) -> None:
        self.macros.append(Macro(name, value, source, text))


SETS = {"J30": "Jthirty", "J60": "Jsixty"}
LAMBDAS = {"0": "LamZero", "0.005": "LamHalf", "0.01": "LamOne", "0.02": "LamTwo"}
CHECKPOINTS = {"0": "Fzero", "0.4": "Ffour", "0.8": "Feight"}
FORECASTERS = {"mc_full": "McFull", "mc_no_future": "McNoFuture", "deterministic": "Det"}
MISSPEC = {"mc_k0.5": "KappaHalf", "mc_k1": "KappaOne", "mc_k2": "KappaTwo"}
MISSPEC |= {"mc_pert_wide": "PertWide"}
METHODS = {
    "SGS-LFT": "SgsLft",
    "SGS-LST": "SgsLst",
    "SGS-MTS": "SgsMts",
    "SGS-GRPW": "SgsGrpw",
    "RBRS-1000": "Rbrs",
    "CP-SAT 1 s": "CpsatOne",
    "CP-SAT 10 s": "CpsatTen",
}
BASELINES = {
    "NoReaction": "NoReaction",
    "AlwaysSubstitute": "AlwaysSubst",
    "FullResolve": "FullResolve",
    "FullResolve(subst)": "FullResolveSubst",
    "StableResolve(subst)": "StableResolveSubst",
}
MAIN_POLICIES = BASELINES | {"Sentinel": "Sentinel", "Sentinel no OT": "SentinelNoOT"}
ABLATION = {
    "Sentinel scalarised": "SentinelScalarised",
    "Sentinel Λ=2": "SentinelGate",
    "Sentinel DESCOPE": "SentinelDescope",
    "Sentinel δ=0.3": "SentinelDeltaThree",
}
LEVELS = {"Sentinel Λ=0": "Zero", "Sentinel Λ=1": "One"}
BACKENDS = {"ollama": "Qwen", "openrouter": "GptOss"}
SOURCES = {"random": "Random", **BACKENDS}
STYLES = {"structured": "Structured", "narrative": "Narrative", "pooled": "Pooled"}
CONDITIONS = {"single shot": "Single", "repair": "Repair"}
EVENT_CONDITIONS = {"single_shot": "Single", "repair": "Repair"}
FACT_KINDS = {
    "chosen_action": "ChosenAction",
    "p_on_time": "POnTime",
    "tardiness_days": "Tardiness",
    "budget_overrun": "BudgetOverrun",
    "alternative": "Alternative",
    "alternative_p_on_time": "AlternativePOnTime",
    "deciding_component": "DecidingComponent",
}
RQ4_SECTIONS = {"J30": "J30 (C*: optimum", "J60": "J60 (C*: best known"}


def rq2_macros(catalog: Catalog, tables: SummaryTables) -> None:
    """RQ2: gaps to the reference, matches, proven optima and runtimes per method and set."""
    for set_name, set_key in SETS.items():
        table = tables.table(set_name)
        catalog.cell(f"RQtwoInstances{set_key}", table, "n", {"Method": "CP-SAT 10 s"})
        for method, key in METHODS.items():
            row = {"Method": method}
            catalog.cell(f"RQtwoGap{key}{set_key}", table, "mean dev_ref %", row)
            catalog.cell(f"RQtwoGapLb{key}{set_key}", table, "mean dev_lb0 %", row)
            catalog.cell(f"RQtwoMatches{key}{set_key}", table, "matches", row)
            catalog.cell(f"RQtwoMatchesPct{key}{set_key}", table, "matches", row, part="share")
            catalog.cell(f"RQtwoTime{key}{set_key}", table, "mean runtime s", row)
            catalog.cell(f"RQtwoTimeMax{key}{set_key}", table, "max runtime s", row)
            if method.startswith("CP-SAT"):
                cell = table.cell("statuses", **row)
                proven = re.search(r"OPTIMAL (\d+)", cell.text)
                catalog.add(
                    f"RQtwoProven{key}{set_key}",
                    proven.group(1) if proven else "0",
                    cell.source(["Method"]) + " (OPTIMAL count)",
                )


def calibration_macros(catalog: Catalog, tables: SummaryTables) -> None:
    """Scenario calibration (WP2b): NoReaction on time per lambda_A and delta_D, C / C*."""
    deltas = {"0.1": "Done", "0.2": "Dtwo", "0.3": "Dthree"}
    for set_name, set_key in SETS.items():
        table = tables.table(f"{set_name} (C*")
        rows = {f"la{lam}_L3": suffix for lam, suffix in LAMBDAS.items()}
        rows["durations_only"] = "DurationsOnly"
        for scenario, suffix in rows.items():
            key = {"Scenario": scenario}
            for delta, d_key in deltas.items():
                catalog.cell(
                    f"CalibOnTime{d_key}{set_key}{suffix}",
                    table,
                    f"On time δ={delta}",
                    key,
                    ci=delta == "0.2",
                )
            catalog.cell(f"CalibCRatio{set_key}{suffix}", table, "C / C*", key)


def rq3_macros(catalog: Catalog, tables: SummaryTables, misspec: SummaryTables) -> None:
    """RQ3: Brier, BSS, ECE, AUC and PIT coverage at f in {0, 0.4, 0.8} per set and forecaster
    (delta_D = 0.2, pooled over lambda_A); paired Brier differences; misspecification."""
    calibration = "Calibration and discrimination of P(C ≤ D), pooled over λ_A"
    makespan = "Makespan distribution, pooled over λ_A"
    paired = "Paired differences, pooled over λ_A"
    for set_name, set_key in SETS.items():
        reference = "optimum" if set_name == "J30" else "best known"
        section = f"{set_name} (C*: {reference}), δ_D = 0.2"
        binary = tables.table(section, calibration)
        spread = tables.table(section, makespan)
        differences = tables.table(section, paired)
        for f, f_key in CHECKPOINTS.items():
            base = {"f": f, "Forecaster": "mc_full"}
            catalog.cell(f"RQthreeOnTime{set_key}{f_key}", binary, "On time", base)
            catalog.cell(f"RQthreeUnc{set_key}{f_key}", binary, "UNC", base)
            catalog.cell(f"RQthreeN{set_key}{f_key}", binary, "N", base)
            for forecaster, fc in FORECASTERS.items():
                row = {"f": f, "Forecaster": forecaster}
                stem = f"{fc}{set_key}{f_key}"
                catalog.cell(f"RQthreeBrier{stem}", binary, "Brier", row, ci=True)
                catalog.cell(f"RQthreeBss{stem}", binary, "BSS", row)
                catalog.cell(f"RQthreeEce{stem}", binary, "ECE", row)
                catalog.cell(f"RQthreeAuc{stem}", binary, "AUC", row)
                catalog.cell(f"RQthreePitCov{stem}", spread, "PIT cov. 80 %", row)
            for other, o_key in (("deterministic", "Det"), ("mc_no_future", "McNoFuture")):
                catalog.cell(
                    f"RQthreeDiffBrier{o_key}{set_key}{f_key}",
                    differences,
                    "ΔBrier",
                    {"f": f, "Difference": f"mc_full - {other}"},
                    ci=True,
                )
    section = "J30 (C*: optimum), δ_D = 0.2"
    binary = misspec.table(section, calibration)
    for f, f_key in CHECKPOINTS.items():
        for forecaster, fc in MISSPEC.items():
            row = {"f": f, "Forecaster": forecaster}
            catalog.cell(f"RQthreeMisspecBrier{fc}{f_key}", binary, "Brier", row)
            catalog.cell(f"RQthreeMisspecEce{fc}{f_key}", binary, "ECE", row)


def _main_table(tables: SummaryTables, section: str) -> Table:
    return tables.table(section, columns=("Runs", "On time δ=0.2 [%]"))


def rq4_macros(catalog: Catalog, runs: Mapping[str, Run]) -> None:
    """RQ4: on time, C / C*, deviation, nervousness, cost / B per policy and set (pooled over
    lambda_A, on time also per lambda_A); paired differences against NoReaction and
    FullResolve; Sentinel's per-run counts; ablation, autonomy levels, sensitivity, baselines."""
    main = runs["rq4_main"].tables
    for set_name, set_key in SETS.items():
        section = RQ4_SECTIONS[set_name]
        table = _main_table(main, section)
        versus = {
            "NoReaction": main.table(section, caption="Paired differences against NoReaction"),
            "FullResolve": main.table(section, caption="Paired differences against FullResolve"),
        }
        per_run = main.table(section, caption="Sentinel per run")
        chosen = main.table(section, caption="Chosen candidates")
        for policy, p_key in MAIN_POLICIES.items():
            row = {"λ_A": "all", "Policy": policy}
            stem = f"{p_key}{set_key}"
            catalog.cell(f"RQfourOnTime{stem}", table, "On time δ=0.2 [%]", row, ci=True)
            catalog.cell(f"RQfourOnTimeDthree{stem}", table, "On time δ=0.3 [%]", row, ci=True)
            catalog.cell(f"RQfourCRatio{stem}", table, "C / C*", row)
            catalog.cell(f"RQfourDeviation{stem}", table, "Deviation [d]", row)
            catalog.cell(f"RQfourNervousness{stem}", table, "Nervousness", row)
            catalog.cell(f"RQfourCostB{stem}", table, "Cost / B", row)
            catalog.cell(f"RQfourSecondsPerRun{stem}", table, "s / run", row)
            for lam, lam_key in LAMBDAS.items():
                catalog.cell(
                    f"RQfourOnTime{stem}{lam_key}",
                    table,
                    "On time δ=0.2 [%]",
                    {"λ_A": lam, "Policy": policy},
                )
            if policy != "NoReaction":
                for column, metric in (
                    ("Δ on time δ=0.2 [pp]", "OnTime"),
                    ("Δ C / C*", "CRatio"),
                    ("Δ deviation [d]", "Deviation"),
                ):
                    catalog.cell(
                        f"RQfourVsNoReaction{metric}{stem}",
                        versus["NoReaction"],
                        column,
                        row,
                        ci=True,
                    )
            if policy.startswith("Sentinel"):
                catalog.cell(
                    f"RQfourVsNoReactionOnTimeDthree{stem}",
                    versus["NoReaction"],
                    "Δ on time δ=0.3 [pp]",
                    row,
                    ci=True,
                )
                for column, metric in (
                    ("Δ on time δ=0.2 [pp]", "OnTime"),
                    ("Δ on time δ=0.3 [pp]", "OnTimeDthree"),
                    ("Δ C / C*", "CRatio"),
                    ("Δ deviation [d]", "Deviation"),
                ):
                    catalog.cell(
                        f"RQfourVsFullResolve{metric}{stem}",
                        versus["FullResolve"],
                        column,
                        row,
                        ci=True,
                    )
                for column, metric in (
                    ("Overtime share", "OvertimeShare"),
                    ("Hired", "Hired"),
                    ("Deliberations", "Deliberations"),
                    ("Gate exits", "GateExits"),
                    ("Rollouts / del.", "RolloutsPerDeliberation"),
                    ("s / del.", "SecondsPerDeliberation"),
                ):
                    catalog.cell(f"RQfour{metric}{stem}", per_run, column, row)
                for column, metric in (
                    ("Needs met", "NeedsMet"),
                    ("NOOP", "ChoseNoop"),
                    ("OVERTIME", "ChoseOvertime"),
                    ("RESEQ", "ChoseReseq"),
                ):
                    catalog.cell(f"RQfour{metric}{stem}", chosen, column, row)
    _ablation_macros(catalog, runs)
    baselines = runs["rq4_baselines"].tables
    for set_name, set_key in SETS.items():
        table = _main_table(baselines, RQ4_SECTIONS[set_name])
        for policy, p_key in BASELINES.items():
            row = {"λ_A": "all", "Policy": policy}
            catalog.cell(
                f"RQfourBaseOnTime{p_key}{set_key}", table, "On time δ=0.2 [%]", row, ci=True
            )
            catalog.cell(f"RQfourBaseCRatio{p_key}{set_key}", table, "C / C*", row)
    sensitivity = runs["rq4_sensitivity"].tables
    table = _main_table(sensitivity, RQ4_SECTIONS["J30"])
    paired = sensitivity.table(RQ4_SECTIONS["J30"], caption="Paired differences against NoReaction")
    for policy, p_key in BASELINES.items():
        row = {"λ_A": "all", "Policy": policy}
        catalog.cell(f"RQfourSensOnTime{p_key}", table, "On time δ=0.2 [%]", row, ci=True)
        if policy != "NoReaction":
            catalog.cell(
                f"RQfourSensVsNoReactionOnTime{p_key}", paired, "Δ on time δ=0.2 [pp]", row, ci=True
            )


def _ablation_macros(catalog: Catalog, runs: Mapping[str, Run]) -> None:
    ablation = runs["rq4_ablation"].tables
    section = RQ4_SECTIONS["J30"]
    table = _main_table(ablation, section)
    versus = ablation.table(section, caption="Paired differences against NoReaction")
    against_full = ablation.table(section, caption="Paired differences against FullResolve")
    for policy, p_key in {
        **ABLATION,
        "NoReaction": "NoReaction",
        "FullResolve": "FullResolve",
    }.items():
        row = {"λ_A": "all", "Policy": policy}
        catalog.cell(f"RQfourAblOnTime{p_key}", table, "On time δ=0.2 [%]", row, ci=True)
        catalog.cell(f"RQfourAblOnTimeDthree{p_key}", table, "On time δ=0.3 [%]", row, ci=True)
        catalog.cell(f"RQfourAblCRatio{p_key}", table, "C / C*", row)
        catalog.cell(f"RQfourAblDeviation{p_key}", table, "Deviation [d]", row)
        catalog.cell(f"RQfourAblNervousness{p_key}", table, "Nervousness", row)
        catalog.cell(f"RQfourAblCostB{p_key}", table, "Cost / B", row)
        if policy in ABLATION:
            catalog.cell(
                f"RQfourAblVsNoReactionOnTime{p_key}", versus, "Δ on time δ=0.2 [pp]", row, ci=True
            )
            catalog.cell(
                f"RQfourAblVsFullResolveOnTime{p_key}",
                against_full,
                "Δ on time δ=0.2 [pp]",
                row,
                ci=True,
            )
    autonomy = runs["rq4_autonomy"].tables
    table = _main_table(autonomy, section)
    for policy, level in {
        **LEVELS,
        "NoReaction": "NoReaction",
        "FullResolve": "FullResolve",
    }.items():
        row = {"λ_A": "0.01", "Policy": policy}
        stem = f"Level{level}" if policy in LEVELS else level
        catalog.cell(f"RQfourAuto{stem}OnTime", table, "On time δ=0.2 [%]", row, ci=True)
        catalog.cell(f"RQfourAuto{stem}Nervousness", table, "Nervousness", row)
        catalog.cell(f"RQfourAuto{stem}Deviation", table, "Deviation [d]", row)
        catalog.cell(f"RQfourAuto{stem}SecondsPerRun", table, "s / run", row)
    table = _main_table(ablation, section)
    row = {"λ_A": "0.01", "Policy": "Sentinel Λ=2"}
    catalog.cell("RQfourAutoLevelTwoOnTime", table, "On time δ=0.2 [%]", row, ci=True)
    catalog.cell("RQfourAutoLevelTwoNervousness", table, "Nervousness", row)
    catalog.cell("RQfourAutoLevelTwoDeviation", table, "Deviation [d]", row)
    catalog.cell("RQfourAutoLevelTwoSecondsPerRun", table, "s / run", row)


def rq1_macros(catalog: Catalog, tables: SummaryTables) -> None:
    """RQ1: valid, exact, edge recall and F1 per backend, style and condition; repair deltas;
    the error analysis (narrative style, rounds 0 and 3)."""
    for backend, b_key in BACKENDS.items():
        section = f"{backend} ("
        main = tables.table(section, header="Style", columns=("Valid [%]", "Condition"))
        deltas = tables.table(section, caption="Paired differences repair - single shot")
        for style, s_key in STYLES.items():
            for condition, c_key in CONDITIONS.items():
                row = {"Style": style, "Condition": condition}
                stem = f"{b_key}{s_key}{c_key}"
                catalog.cell(f"RQoneValid{stem}", main, "Valid [%]", row, ci=True)
                catalog.cell(f"RQoneExact{stem}", main, "Exact [%]", row, ci=True)
                catalog.cell(f"RQoneActRecall{stem}", main, "Act. recall", row)
                catalog.cell(f"RQoneEdgeRecall{stem}", main, "Edge R", row)
                catalog.cell(f"RQoneEdgeFone{stem}", main, "Edge F1", row)
            row = {"Style": style}
            for column, metric in (
                ("Δ valid [pp]", "Valid"),
                ("Δ exact [pp]", "Exact"),
                ("Δ edge F1", "EdgeFone"),
            ):
                catalog.cell(f"RQoneDelta{metric}{b_key}{s_key}", deltas, column, row, ci=True)
    section = "Error analysis: missed precedence edges"
    overview = tables.table(section, caption="Every session replayed")
    sides = tables.table(section, caption="Narrative style, recall by side with 95 % intervals")
    for backend, b_key in BACKENDS.items():
        for round_, r_key in (("0", "RoundZero"), ("3", "RoundThree")):
            row = {"Backend": backend, "Round": round_}
            stem = f"{b_key}{r_key}"
            catalog.cell(f"RQoneErrSuccessor{stem}", sides, "Successor side", row, ci=True)
            catalog.cell(f"RQoneErrPredecessor{stem}", sides, "Predecessor side", row, ci=True)
            catalog.cell(f"RQoneErrGap{stem}", sides, "Successor - predecessor", row, ci=True)
            catalog.cell(
                f"RQoneErrMissedPredecessor{stem}",
                sides,
                "Missed on predecessor side [%]",
                row,
                ci=True,
            )
            full = {"Backend": backend, "Style": "narrative", "Round": round_}
            catalog.cell(f"RQoneErrEdges{stem}", overview, "Edges", full)
            catalog.cell(f"RQoneErrRecall{stem}", overview, "Recall", full)
            catalog.cell(f"RQoneErrMissed{stem}", overview, "Missed", full)
            catalog.cell(
                f"RQoneErrPredecessorBase{stem}", overview, "All on predecessor side [%]", full
            )


def rq5_macros(catalog: Catalog, runs: Mapping[str, Run]) -> None:
    """RQ5: event parsing, proposals against the random control, explanations, online check."""
    events = runs["rq5_events"].tables
    shares = _caption(events, "200 messages")
    types = _caption(events, "Per event type")
    fields = _caption(events, "Field accuracy")
    deltas = _caption(events, "Repair - single shot")
    for backend, b_key in BACKENDS.items():
        for condition, c_key in EVENT_CONDITIONS.items():
            row = {"Backend": backend, "Condition": condition}
            stem = f"{b_key}{c_key}"
            catalog.cell(f"RQfiveEventValid{stem}", shares, "Valid", row, ci=True)
            catalog.cell(f"RQfiveEventExact{stem}", shares, "Exact", row, ci=True)
            catalog.cell(f"RQfiveEventEndToEnd{stem}", shares, "End to end", row, ci=True)
            catalog.cell(f"RQfiveEventNoiseFp{stem}", shares, "Noise false positives", row)
            catalog.cell(f"RQfiveEventLeaks{stem}", shares, "Leaks", row)
            catalog.cell(f"RQfiveEventRawLeaks{stem}", shares, "Raw leaks", row)
            for column, metric in (
                ("absence P", "AbsenceP"),
                ("absence R", "AbsenceR"),
                ("work_increase P", "WorkIncreaseP"),
                ("work_increase R", "WorkIncreaseR"),
                ("new_activity P", "NewActivityP"),
                ("new_activity R", "NewActivityR"),
            ):
                catalog.cell(f"RQfiveEvent{metric}{stem}", types, column, row)
            catalog.cell(f"RQfiveEventReturnDay{stem}", fields, "absence.return_day", row)
        row = {"Backend": backend}
        catalog.cell(f"RQfiveEventDeltaExact{b_key}", deltas, "Exact", row, ci=True)
        catalog.cell(f"RQfiveEventDeltaEndToEnd{b_key}", deltas, "End to end", row, ci=True)
    catalog.cell(
        "RQfiveEventMessages",
        shares,
        "Valid",
        {"Backend": "ollama", "Condition": "repair"},
        part="n",
    )
    proposals = runs["rq5_proposals"].tables
    overview = _caption(proposals, "150 decision states")
    versus = _caption(proposals, "LLM - random")
    for source, s_key in SOURCES.items():
        row = {"Source": source}
        catalog.cell(f"RQfivePropValid{s_key}", overview, "Valid answers", row)
        catalog.cell(f"RQfivePropProposals{s_key}", overview, "Proposals", row)
        catalog.cell(f"RQfivePropCompile{s_key}", overview, "Compile rate", row)
        catalog.cell(f"RQfivePropDuplicate{s_key}", overview, "Duplicate rate", row)
        catalog.cell(f"RQfivePropWinRate{s_key}", overview, "Win rate", row, ci=True)
        catalog.cell(f"RQfivePropGainP{s_key}", overview, "Gain min(p, θ)", row)
        catalog.cell(f"RQfivePropGainPSe{s_key}", overview, "Gain min(p, θ)", row, part="se")
        catalog.cell(f"RQfivePropGainT{s_key}", overview, "Gain T (days)", row)
        catalog.cell(f"RQfivePropGainTSe{s_key}", overview, "Gain T (days)", row, part="se")
        if source != "random":
            for column, metric in (
                ("Win rate", "WinRate"),
                ("Improvement min(p, θ)", "ImprovementP"),
                ("Improvement T (days)", "ImprovementT"),
            ):
                catalog.cell(f"RQfivePropVsRandom{metric}{s_key}", versus, column, row, ci=True)
    explanations = runs["rq5_explanations"].tables
    overview = _caption(explanations, "150 decision states")
    cited = _caption(explanations, "Cited facts per kind")
    for backend, b_key in BACKENDS.items():
        row = {"Backend": backend}
        catalog.cell(f"RQfiveExplValid{b_key}", overview, "Valid", row, ci=True)
        catalog.cell(f"RQfiveExplFaithful{b_key}", overview, "Fully faithful", row, ci=True)
        catalog.cell(f"RQfiveExplChosenCited{b_key}", overview, "Chosen cited", row)
        catalog.cell(f"RQfiveExplComponentRight{b_key}", overview, "Component right", row)
        catalog.cell(
            f"RQfiveExplHallucinated{b_key}", overview, "Hallucinated numbers / expl.", row
        )
        catalog.cell(f"RQfiveExplWords{b_key}", overview, "Words (mean)", row)
        for kind, k_key in FACT_KINDS.items():
            catalog.cell(f"RQfiveExplCorrect{k_key}{b_key}", cited, kind, row)
            catalog.cell(f"RQfiveExplCited{k_key}{b_key}", cited, kind, row, part="denominator")
            catalog.cell(f"RQfiveExplCitedShare{k_key}{b_key}", cited, kind, row, part="share")
    online = runs["rq5_online"].tables.table(header="Backend")
    row = {"Backend": "openrouter"}
    for column, metric in (
        ("Runs", "Runs"),
        ("On time", "OnTime"),
        ("On time WP5", "OnTimeWpFive"),
        ("Makespan - WP5", "DeltaMakespan"),
        ("Deviation - WP5", "DeltaDeviation"),
        ("Cost/B - WP5", "DeltaCostB"),
        ("Gated deliberations", "Deliberations"),
        ("Proposals added", "ProposalsAdded"),
        ("Chosen", "Chosen"),
        ("Tokens / run", "TokensPerRun"),
    ):
        catalog.cell(f"RQfiveOnline{metric}", online, column, row)


def _caption(tables: SummaryTables, caption: str) -> Table:
    return tables.table(caption=caption)


def data_macros(catalog: Catalog, runs: Mapping[str, Run], extra: Mapping[str, Macro]) -> None:
    """Sizes (rows, hours) per run from the manifests, and the machine of the RQ4 main run."""
    names = {
        "rq2": "RQtwo",
        "calibration": "Calib",
        "rq3": "RQthree",
        "rq3_misspec": "RQthreeMisspec",
        "rq4_baselines": "RQfourBaselines",
        "rq4_sensitivity": "RQfourSensitivity",
        "rq4_main": "RQfourMain",
        "rq4_ablation": "RQfourAblation",
        "rq4_autonomy": "RQfourAutonomy",
        "rq1": "RQone",
        "rq5_events": "RQfiveEvents",
        "rq5_proposals": "RQfiveProposals",
        "rq5_explanations": "RQfiveExplanations",
        "rq5_online": "RQfiveOnline",
    }
    for role, stem in names.items():
        run = runs[role]
        manifest = run.manifest
        path = (run.path / "manifest.json").as_posix()
        rows = manifest.get("n_rows", manifest.get("result_rows"))
        if rows is not None:
            catalog.add(f"Data{stem}Rows", str(rows), f"{path} | field n_rows")
        hours = float(manifest["duration_s"]) / 3600
        catalog.add(f"Data{stem}Hours", f"{hours:.1f}", f"{path} | field duration_s / 3600")
    for macro in extra.values():
        catalog.macros.append(macro)
    manifest = runs["rq4_main"].manifest
    path = (runs["rq4_main"].path / "manifest.json").as_posix()
    catalog.add("MachineCpu", str(manifest["cpu"]), f"{path} | field cpu", text=True)
    catalog.add("MachineCores", str(manifest["cpu_count"]), f"{path} | field cpu_count")
    catalog.add("MachinePython", str(manifest["python"]), f"{path} | field python", text=True)
    catalog.add(
        "MachineOrtools",
        str(manifest["packages"]["ortools"]),
        f"{path} | field packages.ortools",
        text=True,
    )


def _escape(text: str) -> str:
    for char in "\\&%$#_{}":
        text = text.replace(char, f"\\{char}" if char != "\\" else r"\textbackslash{}")
    return text.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")


def build_macros(runs: Mapping[str, Run], extra: Mapping[str, Macro]) -> list[Macro]:
    """Every macro, in RQ order."""
    catalog = Catalog()
    rq1_macros(catalog, runs["rq1"].tables)
    rq2_macros(catalog, runs["rq2"].tables)
    rq3_macros(catalog, runs["rq3"].tables, runs["rq3_misspec"].tables)
    calibration_macros(catalog, runs["calibration"].tables)
    rq4_macros(catalog, runs)
    rq5_macros(catalog, runs)
    data_macros(catalog, runs, extra)
    return catalog.macros


# --- Computed values ------------------------------------------------------------------------

LADDER_SCENARIO = "la0.01_L3"


@dataclass(frozen=True)
class LadderPoint:
    """Sentinel full (autonomy level 3) on the worlds of the autonomy study: on time for
    delta_D = 0.2 with its Wilson interval, nervousness, deviation, seconds per run."""

    runs: int
    on_time: str
    low: str
    high: str
    nervousness: str
    deviation: str
    seconds: str
    source: str


def ladder_full(main: Run, autonomy: Run) -> LadderPoint:
    """The runs of `sentinel_full` in the main study on the autonomy study's worlds (J30 every
    8th, lambda_A = 0.01), aggregated by the policy summary's code; the main study's own
    summary prints them only pooled with the other J30 instances."""
    # Imported here so that the paper generator loads the policy summary only when it runs.
    from sentinel.experiments.policy_summary import aggregate, read_results
    from sentinel.experiments.simulation_summary import wilson_interval

    deltas = (0.2, 0.3)
    file = main.path / str(main.manifest["results_file"])
    others = read_results(autonomy.path / str(autonomy.manifest["results_file"]), deltas)
    worlds = {r.world for r in others if r.policy == "sentinel_lambda0"}
    rows = [
        r for r in read_results(file, deltas) if r.policy == "sentinel_full" and r.world in worlds
    ]
    if len(rows) != len(worlds) or any(w[2] != LADDER_SCENARIO for w in worlds):
        raise RunRefused(f"the main study lacks sentinel_full on the {len(worlds)} worlds")
    cell = aggregate(rows, len(deltas))
    low, high = wilson_interval(cell.on_time[0], cell.n)
    source = (
        f"{file.as_posix()} | rows policy=sentinel_full on the {len(worlds)} worlds of "
        f"sentinel_lambda0 in {autonomy.path.as_posix()} (J30, {LADDER_SCENARIO}) | "
        "policy_summary.aggregate"
    )
    return LadderPoint(
        cell.n,
        f"{100 * cell.share(0):.1f}",
        f"{100 * low:.1f}",
        f"{100 * high:.1f}",
        f"{cell.nervousness:.1f}",
        f"{cell.deviation:.2f}",
        f"{cell.runtime_s:.3f}",
        source,
    )


def ladder_macros(point: LadderPoint) -> dict[str, Macro]:
    """The macros of the computed level-3 point."""
    values = {
        "RQfourAutoLevelThreeRuns": (str(point.runs), "runs"),
        "RQfourAutoLevelThreeOnTime": (point.on_time, "column met_0.2, share in %"),
        "RQfourAutoLevelThreeOnTimeLo": (point.low, "Wilson 95 % interval, low"),
        "RQfourAutoLevelThreeOnTimeHi": (point.high, "Wilson 95 % interval, high"),
        "RQfourAutoLevelThreeNervousness": (point.nervousness, "column nervousness, mean"),
        "RQfourAutoLevelThreeDeviation": (point.deviation, "column deviation, mean"),
        "RQfourAutoLevelThreeSecondsPerRun": (point.seconds, "column runtime_s, mean"),
    }
    return {
        name: Macro(name, value, f"{point.source} | {what}")
        for name, (value, what) in values.items()
    }


# --- Tables -------------------------------------------------------------------------------

BACKEND_LABELS = {"ollama": "qwen2.5:7b (Ollama)", "openrouter": "gpt-oss-120b (Groq)"}
FORECASTER_LABELS = {
    "mc_full": "MC, full",
    "mc_no_future": "MC, no future",
    "deterministic": "deterministic",
}
POLISH = {
    "Style": "Styl",
    "Condition": "Wariant",
    "Valid [%]": "Poprawne [\\%]",
    "Exact [%]": "Dokładne [\\%]",
    "Act. rec.": "Czuł. czynn.",
    "Edge R": "Czuł. kraw.",
    "Edge $F_1$": "$F_1$ kraw.",
    "structured": "strukturalny",
    "narrative": "narracyjny",
    "single shot": "jednorazowo",
    "repair": "z naprawą",
    "Method": "Metoda",
    "Gap [%]": "Luka [\\%]",
    "Opt. [%]": "Opt. [\\%]",
    "Best [%]": "Najl. [\\%]",
    "Time [s]": "Czas [s]",
    "Set": "Zbiór",
    "Forecaster": "Prognoza",
    "MC, full": "MC, pełna",
    "MC, no future": "MC, bez przyszłości",
    "deterministic": "deterministyczna",
    "PIT cov.": "Pokr. PIT",
    "Policy": "Polityka",
    "On time [%]": "Na czas [\\%]",
    "on time [pp]": "[p.p.]",
    "instances": "instancji",
    "Dev. [d]": "Odch. [d]",
    "Nerv.": "Nerw.",
    "Cost/B": "Koszt/B",
    "Sentinel no OT": "Sentinel bez OT",
    "Metric": "Miara",
    "random": "losowe",
    "Role 1: events (200 messages, after repair)": (
        "Rola 1: zdarzenia (200 wiadomości, po naprawie)"
    ),
    "Exact [%] (message)": "Dokładne [\\%] (wiadomość)",
    "End to end [%]": "Od końca do końca [\\%]",
    "Absence recall": "Czułość nieobecności",
    "Return-day accuracy": "Trafność dnia powrotu",
    "Reason words accepted": "Słowa o przyczynie przyjęte",
    "Role 2: proposals (150 decision states)": "Rola 2: propozycje (150 stanów decyzyjnych)",
    "Compile rate [%]": "Skompilowane [\\%]",
    "Duplicate rate [%]": "Duplikaty [\\%]",
    "Win rate [%]": "Wygrane [\\%]",
    "LLM $-$ random [pp]": "LLM $-$ losowe [p.p.]",
    "Role 3: explanations (150 decision states)": "Rola 3: wyjaśnienia (150 stanów decyzyjnych)",
    "Fully faithful [%]": "W pełni wierne [\\%]",
    "Hallucinated numbers": "Zmyślone liczby",
    "Words": "Słowa",
}
POLISH_LANGUAGE = Language("pl", "{,}", "; ", "\\,", POLISH)


def _get(table: Table, column: str, key: Mapping[str, str]) -> Parts:
    return parse_cell(table.cell(column, **key).text)


def _num(parts: Parts, language: Language, *, ci: bool = False) -> str:
    text = language.number(parts.value)
    if ci and parts.low is not None and parts.high is not None:
        text += " " + language.interval(parts.low, parts.high)
    return text


def _tabular(spec: str, header: Sequence[str], body: Sequence[str], notes: Sequence[str]) -> str:
    lines = [
        "% Generated by sentinel.experiments.paper from configs/paper.toml; do not edit.",
        *(f"% {note}" for note in notes),
        "% Typeset with \\small; intervals in \\tiny.",
        r"{\setlength{\tabcolsep}{3pt}%",
        rf"\begin{{tabular}}{{{spec}}}",
        r"\toprule",
        *header,
        r"\midrule",
        *body,
        r"\bottomrule",
        r"\end{tabular}}",
    ]
    return "\n".join(lines) + "\n"


def tab_rq1(runs: Mapping[str, Run], language: Language) -> str:
    """RQ1: per backend and style (group rows) and condition: valid and exact shares, edge
    recall and F1; Delta rows: repair - single shot (95 % cluster bootstrap intervals)."""
    tables = runs["rq1"].tables
    say = language.label
    header = [
        f"{say('Condition')} & {say('Valid [%]')} & {say('Exact [%]')} & {say('Edge R')} & "
        f"{say('Edge $F_1$')} \\\\"
    ]
    body: list[str] = []
    for backend in BACKENDS:
        main = tables.table(f"{backend} (", header="Style", columns=("Valid [%]", "Condition"))
        deltas = tables.table(f"{backend} (", caption="Paired differences repair - single shot")
        for style in ("structured", "narrative"):
            if body:
                body.append(r"\midrule")
            group = f"{BACKEND_LABELS[backend]}, {say(style)}"
            body.append(rf"\multicolumn{{5}}{{@{{}}l}}{{\textit{{{group}}}}} \\")
            for condition in ("single shot", "repair"):
                key = {"Style": style, "Condition": condition}
                body.append(
                    f"{say(condition)} & "
                    f"{_num(_get(main, 'Valid [%]', key), language, ci=True)} & "
                    f"{_num(_get(main, 'Exact [%]', key), language, ci=True)} & "
                    f"{_num(_get(main, 'Edge R', key), language)} & "
                    f"{_num(_get(main, 'Edge F1', key), language)} \\\\"
                )
            key = {"Style": style}
            body.append(
                rf"$\Delta$ & {_num(_get(deltas, 'Δ valid [pp]', key), language, ci=True)} & "
                f"{_num(_get(deltas, 'Δ exact [pp]', key), language, ci=True)} & & "
                f"{_num(_get(deltas, 'Δ edge F1', key), language, ci=True)} \\\\"
            )
    notes = [
        f"RQ1 ({runs['rq1'].path.as_posix()}): 40 J30 instances per style; Valid, Exact: share",
        "of sessions in % (95 % Wilson); Delta: repair - single shot, percentage points and",
        "score differences (95 % cluster bootstrap over instances).",
    ]
    return _tabular("@{}lrrrr@{}", header, body, notes)


def tab_rq2(runs: Mapping[str, Run], language: Language) -> str:
    """RQ2: mean gap to the reference, share of instances at the reference and mean runtime per
    method, J30 (optimum) and J60 (best known)."""
    tables = runs["rq2"].tables
    say = language.label
    header = [
        r" & \multicolumn{3}{c}{J30} & \multicolumn{3}{c}{J60} \\",
        r"\cmidrule(lr){2-4}\cmidrule(l){5-7}",
        f"{say('Method')} & {say('Gap [%]')} & {say('Opt. [%]')} & {say('Time [s]')} & "
        f"{say('Gap [%]')} & {say('Best [%]')} & {say('Time [s]')} \\\\",
    ]
    body = []
    for method in METHODS:
        cells = []
        for set_name in SETS:
            table = tables.table(set_name)
            key = {"Method": method}
            share = _get(table, "matches", key).share
            cells += [
                _num(_get(table, "mean dev_ref %", key), language),
                language.number(str(share)),
                _num(_get(table, "mean runtime s", key), language),
            ]
        body.append(f"{method} & " + " & ".join(cells) + r" \\")
    notes = [
        f"RQ2 ({runs['rq2'].path.as_posix()}): 480 instances per set; Gap: mean deviation from",
        "the reference makespan in %; Opt./Best: share of instances at the reference.",
    ]
    return _tabular("@{}lrrrrrr@{}", header, body, notes)


def tab_rq3(runs: Mapping[str, Run], language: Language) -> str:
    """RQ3: scores of P(C <= D) and PIT coverage per set, checkpoint and forecaster."""
    tables = runs["rq3"].tables
    say = language.label
    header = [
        f"{say('Set')} & $f$ & {say('Forecaster')} & Brier & BSS & ECE & AUC & "
        f"{say('PIT cov.')} \\\\"
    ]
    body: list[str] = []
    for set_name in SETS:
        reference = "optimum" if set_name == "J30" else "best known"
        section = f"{set_name} (C*: {reference}), δ_D = 0.2"
        binary = tables.table(section, "Calibration and discrimination of P(C ≤ D)")
        spread = tables.table(section, "Makespan distribution, pooled over λ_A")
        if body:
            body.append(r"\midrule")
        for i, f in enumerate(CHECKPOINTS):
            for j, forecaster in enumerate(FORECASTERS):
                key = {"f": f, "Forecaster": forecaster}
                first = set_name if i == j == 0 else ""
                body.append(
                    f"{first} & {language.number(f) if j == 0 else ''} & "
                    f"{say(FORECASTER_LABELS[forecaster])} & "
                    f"{_num(_get(binary, 'Brier', key), language, ci=True)} & "
                    f"{_num(_get(binary, 'BSS', key), language)} & "
                    f"{_num(_get(binary, 'ECE', key), language)} & "
                    f"{_num(_get(binary, 'AUC', key), language)} & "
                    f"{_num(_get(spread, 'PIT cov. 80 %', key), language)} \\\\"
                )
    notes = [
        f"RQ3 ({runs['rq3'].path.as_posix()}): delta_D = 0.2, pooled over lambda_A; Brier with",
        "its 95 % cluster bootstrap interval; PIT cov.: share of PIT values in [0.1, 0.9].",
    ]
    return _tabular("@{}llllrrrr@{}", header, body, notes)


def tab_rq4(runs: Mapping[str, Run], language: Language) -> str:
    """RQ4: per set (group rows) and policy, pooled over lambda_A: on time (delta_D = 0.2)
    with its Wilson interval, the paired difference against NoReaction, C / C*, deviation,
    nervousness and cost / B."""
    tables = runs["rq4_main"].tables
    say = language.label
    header = [
        f"{say('Policy')} & {say('On time [%]')} & $\\Delta$ {say('on time [pp]')} & $C/C^*$ & "
        f"{say('Dev. [d]')} & {say('Nerv.')} & {say('Cost/B')} \\\\"
    ]
    body: list[str] = []
    counts = {"J30": "120", "J60": "60"}
    for set_name in SETS:
        section = RQ4_SECTIONS[set_name]
        main = _main_table(tables, section)
        versus = tables.table(section, caption="Paired differences against NoReaction")
        if body:
            body.append(r"\midrule")
        group = f"{set_name} ({counts[set_name]} {say('instances')})"
        body.append(rf"\multicolumn{{7}}{{@{{}}l}}{{\textit{{{group}}}}} \\")
        for policy in MAIN_POLICIES:
            key = {"λ_A": "all", "Policy": policy}
            delta = (
                "--"
                if policy == "NoReaction"
                else _num(_get(versus, "Δ on time δ=0.2 [pp]", key), language, ci=True)
            )
            body.append(
                f"{say(policy)} & "
                f"{_num(_get(main, 'On time δ=0.2 [%]', key), language, ci=True)} & {delta} & "
                f"{_num(_get(main, 'C / C*', key), language)} & "
                f"{_num(_get(main, 'Deviation [d]', key), language)} & "
                f"{_num(_get(main, 'Nervousness', key), language)} & "
                f"{_num(_get(main, 'Cost / B', key), language)} \\\\"
            )
    notes = [
        f"RQ4 ({runs['rq4_main'].path.as_posix()}): 4 lambda_A x 4 replications per instance;",
        "on time in % with 95 % Wilson intervals; Delta: paired difference against NoReaction",
        "in percentage points (95 % cluster bootstrap over instances).",
    ]
    return _tabular("@{}lrrrrrr@{}", header, body, notes)


def tab_rq5(runs: Mapping[str, Run], language: Language) -> str:
    """RQ5: the LLM's three roles per source: event parsing after repair, proposals against the
    random control, explanations."""
    say = language.label
    events = runs["rq5_events"].tables
    shares, types = _caption(events, "200 messages"), _caption(events, "Per event type")
    fields = _caption(events, "Field accuracy")
    proposals = runs["rq5_proposals"].tables
    overview, versus = (
        _caption(proposals, "150 decision states"),
        _caption(proposals, "LLM - random"),
    )
    explanations = _caption(runs["rq5_explanations"].tables, "150 decision states")
    models = " & ".join(BACKEND_LABELS[b] for b in BACKENDS)
    header = [f"{say('Metric')} & {say('random')} & {models} \\\\"]
    body: list[str] = []

    def block(title: str) -> None:
        if body:
            body.append(r"\midrule")
        body.append(rf"\multicolumn{{4}}{{@{{}}l}}{{\textit{{{say(title)}}}}} \\")

    def row(label: str, cells: Sequence[str]) -> None:
        body.append(f"{say(label)} & " + " & ".join(cells) + r" \\")

    def events_row(label: str, table: Table, column: str, *, ci: bool = False) -> None:
        cells = [
            _num(_get(table, column, {"Backend": b, "Condition": "repair"}), language, ci=ci)
            for b in BACKENDS
        ]
        row(label, ["--", *cells])

    block("Role 1: events (200 messages, after repair)")
    events_row("Exact [%] (message)", shares, "Exact", ci=True)
    events_row("End to end [%]", shares, "End to end", ci=True)
    events_row("Absence recall", types, "absence R")
    events_row("Return-day accuracy", fields, "absence.return_day")
    events_row("Reason words accepted", shares, "Leaks")
    block("Role 2: proposals (150 decision states)")
    for label, column, ci in (
        ("Compile rate [%]", "Compile rate", False),
        ("Duplicate rate [%]", "Duplicate rate", False),
        ("Win rate [%]", "Win rate", True),
    ):
        row(label, [_num(_get(overview, column, {"Source": s}), language, ci=ci) for s in SOURCES])
    row(
        "LLM $-$ random [pp]",
        [
            "--",
            *(_num(_get(versus, "Win rate", {"Source": b}), language, ci=True) for b in BACKENDS),
        ],
    )
    block("Role 3: explanations (150 decision states)")
    for label, column, ci in (
        ("Fully faithful [%]", "Fully faithful", True),
        ("Hallucinated numbers", "Hallucinated numbers / expl.", False),
        ("Words", "Words (mean)", False),
    ):
        row(
            label,
            [
                "--",
                *(
                    _num(_get(explanations, column, {"Backend": b}), language, ci=ci)
                    for b in BACKENDS
                ),
            ],
        )
    notes = [
        "RQ5: events "
        f"{runs['rq5_events'].path.as_posix()}, proposals {runs['rq5_proposals'].path.as_posix()},",
        f"explanations {runs['rq5_explanations'].path.as_posix()}; shares in % with 95 % Wilson",
        "intervals; LLM - random: paired by state (95 % bootstrap over states).",
    ]
    return _tabular("@{}lrrr@{}", header, body, notes)


TABLES: dict[str, Callable[[Mapping[str, Run], Language], str]] = {
    "tab_rq1.tex": tab_rq1,
    "tab_rq2.tex": tab_rq2,
    "tab_rq3.tex": tab_rq3,
    "tab_rq4.tex": tab_rq4,
    "tab_rq5.tex": tab_rq5,
}


# --- Generation ----------------------------------------------------------------------------


def numbers_md(macros: Sequence[Macro]) -> str:
    """`numbers.md`: every macro, its English value and source, for checking."""
    lines = [
        "# Paper macros",
        "",
        "Generated by `sentinel.experiments.paper` from `configs/paper.toml`; do not edit.",
        "",
        "| Macro | Value | Source |",
        "| --- | ---: | --- |",
    ]
    for macro in macros:
        source = macro.source.replace("|", "\\|")
        lines.append(f"| `\\{macro.name}` | {macro.value} | {source} |")
    return "\n".join(lines) + "\n"


def generate(
    config_path: Path, out_dir: Path | None = None, *, pinned: Mapping[str, Any] | None = None
) -> list[Path]:
    """Write every artifact (English in `out_dir`, Polish in `out_dir/pl`) and MANIFEST.json;
    `pinned` is a recorded MANIFEST.json whose provenance is kept (`reproduce --check`)."""
    # Imported here so that `sentinel paper --help` does not load matplotlib.
    from sentinel.experiments import paper_figures

    git, _ = summary_provenance(GIT_EXCLUDE, _manifest_provenance(pinned))
    config = PaperConfig.model_validate(load_toml(config_path))
    target = out_dir or config.out_dir
    runs = load_runs(config)
    point = ladder_full(runs["rq4_main"], runs["rq4_autonomy"])
    macros = build_macros(runs, ladder_macros(point))
    written: list[Path] = []
    for language, folder in ((ENGLISH, target), (POLISH_LANGUAGE, target / "pl")):
        folder.mkdir(parents=True, exist_ok=True)
        texts = {"numbers.tex": numbers_tex(macros, language)}
        texts |= {name: build(runs, language) for name, build in TABLES.items()}
        if language is ENGLISH:
            texts["numbers.md"] = numbers_md(macros)
        for name, text in texts.items():
            (folder / name).write_text(text, encoding="utf-8")
            written.append(folder / name)
        written += paper_figures.write_figures(runs, point, language.code, folder)
    record = {
        "generator": "sentinel.experiments.paper",
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "git_dirty_ignores": list(GIT_EXCLUDE),
        "config": _record(config_path),
        "macros": len(macros),
        "inputs": [
            {
                "role": role,
                "run": run.path.as_posix(),
                "files": [
                    _record(run.path / name)
                    for name in sorted({*config.runs[role].sha256, "summary.md"})
                ],
            }
            for role, run in runs.items()
        ],
        "outputs": [_record(path, target) for path in sorted(written)],
    }
    write_json(target / MANIFEST_NAME, record)
    return [*written, target / MANIFEST_NAME]


def _manifest_provenance(pinned: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if pinned is None:
        return None
    return {"git_commit": pinned.get("git_commit"), "git_dirty": pinned.get("git_dirty")}


def _record(path: Path, root: Path | None = None) -> dict[str, Any]:
    """Path (relative to `root`, else to the working directory when inside it), size and
    SHA-256 of a file; relative paths keep MANIFEST.json independent of the checkout's place."""
    base = root if root is not None else Path.cwd()
    try:
        shown = path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        shown = path.as_posix()
    return {"path": shown, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
