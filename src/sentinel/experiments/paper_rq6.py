"""The paper artifacts of RQ6 (WP20): macros, table and figure of the editing study, from the
run pinned in `configs/paper_rq6.toml`, into `paper/generated/rq6/` (English) and its `pl/`.

They are kept apart from `configs/paper.toml` and `paper/generated/` so that the artifacts of
the earlier studies stay byte for byte as they are; `sentinel paper` writes both, and
`sentinel reproduce --check` checks both. `pin` writes the config for a completed full run (the
SHA-256 of its manifest and raw outputs), as `configs/paper.toml` pins the other runs.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sentinel.experiments.paper import (
    ENGLISH,
    GIT_EXCLUDE,
    MANIFEST_NAME,
    POLISH_LANGUAGE,
    Catalog,
    Language,
    Macro,
    PaperConfig,
    Run,
    _get,
    _num,
    _record,
    _tabular,
    data_files,
    numbers_tex,
    sha256_file,
    verify_run,
)
from sentinel.experiments.runs import load_toml, summary_provenance, write_json
from sentinel.experiments.summary_tables import Table

DEFAULT_CONFIG = Path("configs/paper_rq6.toml")
ROLE = "rq6"
BACKENDS = {"ollama": "Qwen", "openrouter": "GptOss"}
AUDIENCES = {"edit": "Edit", "board": "Board", "finance": "Finance", "team": "Team", "all": "All"}
MODELS = {"ollama": "qwen2.5:7b", "openrouter": "gpt-oss-120b"}
AUDIENCE_NAMES = {
    "en": {
        "edit": "Editing only",
        "board": "Board",
        "finance": "Finance",
        "team": "Team",
        "all": "All four",
    },
    "pl": {
        "edit": "Tylko redakcja",
        "board": "Zarząd",
        "finance": "Finanse",
        "team": "Zespół",
        "all": "Wszystkie",
    },
}
HEADERS = {
    "en": (
        r"Model & Audience & Changed fact & Changed/100 & New fact & Omitted/100 & "
        r"Diff listed \\"
    ),
    "pl": (
        r"Model & Odbiorca & Zmieniony fakt & Zmienione/100 & Nowy fakt & Pominięte/100 & "
        r"Zmiany na liście \\"
    ),
}
NOTES = {
    "en": "shares of versions in %; per 100 facts; intervals: 95 % cluster bootstrap",
    "pl": "udziały wersji w %; na 100 faktów; przedziały: 95 % bootstrap po raportach",
}
PLAIN = "Facts in the edited versions (the application's prompt)"
SELF = "Facts when the model also lists its changes"
LISTED = "The model's own list of changes against the code diff"


def _tables(run: Run) -> tuple[Table, Table, Table]:
    tables = run.tables
    return (
        tables.table(PLAIN, header="Backend"),
        tables.table(SELF, header="Backend"),
        tables.table(LISTED, header="Backend"),
    )


def _backends(table: Table) -> list[str]:
    """The backends of a table, in the order of the paper."""
    column = table.header.index("Backend")
    return [b for b in BACKENDS if b in {row[column] for row in table.rows}]


def build_macros(run: Run) -> list[Macro]:
    """Every RQ6 macro: per backend and audience the facts of both conditions and the model's
    list against the diff, and the run's size."""
    catalog = Catalog()
    plain, self_report, listed = _tables(run)
    backends = _backends(plain)
    for backend in backends:
        for audience, a_key in AUDIENCES.items():
            row = {"Backend": backend, "Audience": audience}
            stem = f"{BACKENDS[backend]}{a_key}"
            for table, prefix in ((plain, "RQsix"), (self_report, "RQsixSelf")):
                catalog.cell(f"{prefix}Valid{stem}", table, "Valid", row)
                catalog.cell(
                    f"{prefix}ChangedVersions{stem}", table, "With a changed fact", row, ci=True
                )
                catalog.cell(
                    f"{prefix}ChangedPerHundred{stem}", table, "Changed per 100 facts", row, ci=True
                )
                catalog.cell(f"{prefix}NewVersions{stem}", table, "With a new fact", row, ci=True)
                catalog.cell(f"{prefix}NewPerVersion{stem}", table, "New per version", row)
                catalog.cell(
                    f"{prefix}OmittedPerHundred{stem}", table, "Omitted per 100 facts", row, ci=True
                )
                catalog.cell(f"{prefix}Length{stem}", table, "Length ratio", row)
            catalog.cell(f"RQsixDiffChanges{stem}", listed, "Diff changes per version", row)
            catalog.cell(f"RQsixListedPerVersion{stem}", listed, "Listed per version", row)
            catalog.cell(f"RQsixDiffListed{stem}", listed, "Diff changes listed", row, ci=True)
            catalog.cell(
                f"RQsixListedNotInDiff{stem}", listed, "Listed not in the diff", row, ci=True
            )
            cell = listed.cell("Changed facts listed", **row)
            if cell.text != "-":
                catalog.cell(
                    f"RQsixChangedFactsListed{stem}", listed, "Changed facts listed", row, ci=True
                )
    manifest = run.manifest
    path = (run.path / "manifest.json").as_posix()
    catalog.add("RQsixReports", str(manifest["n_reports"]), f"{path} | field n_reports")
    catalog.add("DataRQsixRows", str(manifest["n_rows"]), f"{path} | field n_rows")
    hours = float(manifest["duration_s"]) / 3600
    catalog.add("DataRQsixHours", f"{hours:.1f}", f"{path} | field duration_s / 3600")
    return catalog.macros


def tab_rq6(run: Run, language: Language) -> str:
    """Per model and audience, the application's prompt: versions with a changed fact, changed
    facts per 100, versions with a new fact, omitted per 100, and the share of the diff's
    changes the model lists when asked."""
    plain, _, listed = _tables(run)
    code = language.code
    body = []
    for backend in _backends(plain):
        for audience in AUDIENCES:
            row = {"Backend": backend, "Audience": audience}
            cells = [
                _num(_get(plain, "With a changed fact", row), language, ci=True),
                _num(_get(plain, "Changed per 100 facts", row), language),
                _num(_get(plain, "With a new fact", row), language, ci=True),
                _num(_get(plain, "Omitted per 100 facts", row), language),
                _num(_get(listed, "Diff changes listed", row), language, ci=True),
            ]
            name = f"{MODELS[backend]} & {AUDIENCE_NAMES[code][audience]}"
            body.append(f"{name} & " + " & ".join(cells) + r" \\")
    text = _tabular(
        "llrrrrr", [HEADERS[code]], body, [f"from {run.path.as_posix()}; {NOTES[code]}"]
    )
    return text.replace("configs/paper.toml", DEFAULT_CONFIG.as_posix())


def generate(
    config_path: Path = DEFAULT_CONFIG,
    out_dir: Path | None = None,
    *,
    pinned: Mapping[str, Any] | None = None,
) -> list[Path]:
    """Write the RQ6 artifacts (English in `out_dir`, Polish in `out_dir/pl`) and their
    MANIFEST.json; `pinned` is a recorded MANIFEST.json whose provenance is kept."""
    from sentinel.experiments import rq6_study
    from sentinel.experiments.rq5_common import read_rows

    provenance = (
        None
        if pinned is None
        else {
            "git_commit": pinned.get("git_commit"),
            "git_dirty": pinned.get("git_dirty"),
        }
    )
    git, _ = summary_provenance(GIT_EXCLUDE, provenance)
    config = PaperConfig.model_validate(load_toml(config_path))
    target = out_dir or config.out_dir
    run = verify_run(ROLE, config.runs[ROLE])
    macros = build_macros(run)
    rows = read_rows(run.path / rq6_study.RESULTS_FILE)
    study = rq6_study.Rq6Config.model_validate(run.manifest["config"])
    written: list[Path] = []
    for language, folder in ((ENGLISH, target), (POLISH_LANGUAGE, target / "pl")):
        folder.mkdir(parents=True, exist_ok=True)
        numbers = numbers_tex(macros, language).replace(
            "configs/paper.toml", config_path.as_posix()
        )
        texts = {"numbers.tex": numbers, "tab_rq6.tex": tab_rq6(run, language)}
        for name, text in texts.items():
            (folder / name).write_text(text, encoding="utf-8")
            written.append(folder / name)
        for name in rq6_study.write_figure(
            folder, rows, study, language=language.code, pdf_only=True
        ):
            written.append(folder / name)
    record = {
        "generator": "sentinel.experiments.paper_rq6",
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "git_dirty_ignores": list(GIT_EXCLUDE),
        "config": _record(config_path),
        "macros": len(macros),
        "inputs": [
            {
                "role": ROLE,
                "run": run.path.as_posix(),
                "files": [
                    _record(run.path / name)
                    for name in sorted({*config.runs[ROLE].sha256, "summary.md"})
                ],
            }
        ],
        "outputs": [_record(path, target) for path in sorted(written)],
    }
    write_json(target / MANIFEST_NAME, record)
    return [*written, target / MANIFEST_NAME]


def pin(
    run_dir: Path, config_path: Path = DEFAULT_CONFIG, out_dir: str = "paper/generated/rq6"
) -> str:
    """Write the config that pins a completed full run (its manifest and raw outputs by
    SHA-256); returns its text."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    pins = "\n".join(
        f'"{name}" = "{sha256_file(run_dir / name)}"  # pragma: allowlist secret'
        for name in data_files(manifest)
    )
    text = (
        "# Paper artifacts of RQ6 (WP20): the editing study's full run, kept apart from\n"
        "# configs/paper.toml so that the earlier artifacts stay byte for byte as they are.\n"
        "# Written by `uv run sentinel paper --pin-rq6 <run>`; `sentinel paper` and\n"
        "# `sentinel reproduce --check` read it when it exists.\n"
        'name = "paper_rq6"\n'
        f'out_dir = "{out_dir}"\n\n'
        f"[runs.{ROLE}]  # RQ6: editing for audiences, both backends (WP20)\n"
        f'path = "{run_dir.as_posix()}"\n\n'
        f"[runs.{ROLE}.sha256]\n{pins}\n"
    )
    config_path.write_text(text, encoding="utf-8")
    return text


def runs_of(config_path: Path) -> Sequence[Run]:
    """The pinned RQ6 run, verified (for `reproduce`)."""
    config = PaperConfig.model_validate(load_toml(config_path))
    return [verify_run(ROLE, config.runs[ROLE])]
