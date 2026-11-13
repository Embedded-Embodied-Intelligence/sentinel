"""RQ6 (WP20): does AI editing for audiences preserve the facts? (spec section 11.9, ADR-0038)

    uv run python -m sentinel.experiments.rq6_study \
        --config configs/wp20_rq6.toml --out results/wp20 [--backend ollama] [--limit N] \
        [--cache-file <bundle>] [--replay ollama=<file>]

Every report of the corpus (`configs/wp20_rq6_corpus.json`, synthetic; plus the reports a person
put in `own_dir`) is edited for each audience by each selected backend in two conditions:
`plain`, the application's prompt (the edited text only), and `self_report`, the same prompt
asking also for the model's list of its changes. The fact guard (`sentinel.interpret.facts`)
compares each version with the report: changed facts (the dangerous error), new facts (possible
inventions), omitted facts (reported, not an error); and the length. In `self_report` the
model's list is located in the two texts and compared with the code diff
(`sentinel.interpret.tracked`): the share of the diff's changes it reports, the reported changes
that are in no change of the diff or cannot be found, and the share of the changed facts it
reports. Intervals: 95 % cluster bootstrap over reports. Outputs: `results.csv` (one row per
report, audience, backend and condition; no text), `summary.md`, the LaTeX table, the figure
`fig_rq6.pdf`/`.png`, `manifest.json` and the replay bundle (none when a report of a person is
in the run).
"""

import csv
import hashlib
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field

from sentinel.experiments import runs
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.report_corpus import Report, check_report, load_corpus
from sentinel.experiments.rq5_common import (
    BUNDLE_FILE,
    PROGRESS_INTERVAL_S,
    Answer,
    Clients,
    FakeBackend,
    LlmStudyConfig,
    item_seed,
    manifest,
    open_clients,
    read_rows,
    resamples,
    run_main,
    text_rng_seed,
    write_run_bundle,
)
from sentinel.forecasting.metrics import FloatArray, percentile_interval, resampled_ratio
from sentinel.interpret.facts import Guard, check
from sentinel.interpret.redaction import (
    FORMAT_CHANGES_PROMPT,
    FORMAT_PROMPT,
    REDACT_PROMPT,
    STYLE_PROMPT,
    Audience,
    RedactSettings,
    redact,
    redact_reporting,
)
from sentinel.interpret.tracked import Diff, diff, tokenize
from sentinel.llm import LlmResponse, load_prompt

RESULTS_FILE = "results.csv"
SUMMARY_FILE = "summary.md"
FIGURE = "fig_rq6"
Condition = Literal["plain", "self_report"]
COLUMNS = (
    "report",
    "source",
    "audience",
    "condition",
    "backend",
    "model",
    "valid",
    "facts",
    "unchanged",
    "changed",
    "omitted",
    "new",
    "words_report",
    "words_version",
    "code_changes",
    "reported",
    "code_reported",
    "reported_phantom",
    "unlocated",
    "fact_changes_reported",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
)
SEED_RULE = (
    "LLM seed of an edit: runs.derive_seed(base_seed, 'llm', 'rq6', report id, audience), "
    "shared by the backends and the two conditions"
)
AUDIENCE_LABELS = {"edit": "Editing only", "board": "Board", "finance": "Finance", "team": "Team"}
Row = dict[str, Any]


class Rq6Config(LlmStudyConfig):
    """The RQ6 study (configs/wp20_rq6.toml)."""

    corpus: Path
    own_dir: Path | None = None
    audiences: tuple[Audience, ...] = Field(min_length=1)
    conditions: tuple[Condition, ...] = Field(min_length=1)
    redaction: RedactSettings


def load_reports(config: Rq6Config, limit: int | None) -> tuple[list[Report], int]:
    """The corpus (checked: the fact guard finds exactly each report's facts) and the reports of
    a person (`own_dir/*.json`, the same format), the first `limit` of the corpus in a smoke
    run; returns them and the number added by hand."""
    reports = load_corpus(config.corpus)
    issues = [issue for report in reports for issue in check_report(report)]
    if issues:
        raise ValueError("the corpus does not match the fact guard:\n" + "\n".join(issues))
    if limit is not None:
        reports = reports[:limit]
    own: list[Report] = []
    if config.own_dir is not None and config.own_dir.is_dir():
        for path in sorted(config.own_dir.glob("*.json")):
            own += load_corpus(path, source="own")
    if own and config.store_prompts:
        raise ValueError(
            f"{len(own)} reports of a person in {config.own_dir}: set store_prompts = false "
            "(real text never enters a cache record, spec section 10)"
        )
    return reports + own, len(own)


def oracle_answer(report: Report, audience: Audience, condition: Condition, rate: float) -> str:
    """The scripted editor of smoke runs: drops the filler and the repetitions, for the board
    the plan's last sentence too; with probability `rate` changes a number, and with the same
    probability adds a sentence with a figure the report lacks; in `self_report` lists its
    changes, forgetting the changed number."""
    rng = np.random.default_rng(text_rng_seed("rq6", report.id, audience))
    sentences = re.split(r"(?<=[.!?])\s+", report.text)
    drop = [
        s for s in sentences if s.startswith(("Ogólnie", "Jak wspomniano", "Warto", "Na koniec"))
    ]
    if audience == "board":
        drop += [s for s in sentences if s.startswith("Zadaniem")]
    text = report.text
    changes: list[dict[str, str]] = []
    for sentence in drop:
        text = text.replace(sentence + " ", "").replace(" " + sentence, "")
        changes.append({"before": sentence, "after": ""})
    if rng.random() < rate:
        match = re.search(r"(?<![\d,.])(\d+) dni", text)
        if match:
            text = text[: match.start(1)] + str(int(match[1]) + 1) + text[match.end(1) :]
    if rng.random() < rate:
        text += "\n\nRezerwa wynosi 7 %."
        changes.append({"before": "", "after": "Rezerwa wynosi 7 %."})
    answer: dict[str, Any] = {"text": text}
    if condition == "self_report":
        answer["changes"] = changes
    return json.dumps(answer, ensure_ascii=False)


def _fixed(answer: str) -> Answer:
    """The oracle's answer in every round."""

    def respond(round_index: int) -> str:
        return answer

    return respond


def _token_sets(found: Diff) -> tuple[list[set[int]], list[set[int]]]:
    """Per change of the diff, its tokens in the report and in the version."""
    return (
        [set(range(c.a0, c.a1)) for c in found.changes],
        [set(range(c.b0, c.b1)) for c in found.changes],
    )


def _locate(
    text: str, words: str, after: int, offsets: Sequence[int], lengths: Sequence[int]
) -> tuple[set[int], int] | None:
    """The tokens of `words` in `text`, at or after character `after` if possible, and the end
    of the match; None when the words are not in the text (white space compared loosely)."""
    pattern = r"\s+".join(re.escape(part) for part in words.split())
    if not pattern:
        return set(), after
    match = re.compile(pattern).search(text, after) or re.compile(pattern).search(text)
    if match is None:
        return None
    tokens = {
        i
        for i, (start, size) in enumerate(zip(offsets, lengths, strict=True))
        if start < match.end() and match.start() < start + size
    }
    return tokens, match.end()


def self_report(
    report: str, version: str, found: Diff, guard: Guard, reported: Sequence[Mapping[str, str]]
) -> dict[str, int]:
    """The model's list against the code diff: changes of the diff it covers, reported changes
    in no change of the diff, reported changes not found in the texts, changed facts it
    reports."""
    tokens_a, at_a = tokenize(report)
    tokens_b, at_b = tokenize(version)
    sizes_a = [len(t.text) for t in tokens_a]
    sizes_b = [len(t.text) for t in tokens_b]
    code_a, code_b = _token_sets(found)
    covered_a: set[int] = set()
    covered_b: set[int] = set()
    unlocated = phantom = 0
    pos_a = pos_b = 0
    for change in reported:
        before = _locate(report, change.get("before", ""), pos_a, at_a, sizes_a)
        after = _locate(version, change.get("after", ""), pos_b, at_b, sizes_b)
        if before is None or after is None or not (before[0] or after[0]):
            unlocated += 1
            continue
        (in_a, pos_a), (in_b, pos_b) = before, after
        covered_a |= in_a
        covered_b |= in_b
        if not any(in_a & a or in_b & b for a, b in zip(code_a, code_b, strict=True)):
            phantom += 1
    code_reported = sum(
        bool(a & covered_a or b & covered_b) for a, b in zip(code_a, code_b, strict=True)
    )
    facts_reported = 0
    for fact_check in guard.checks:
        if fact_check.state != "changed":
            continue
        if any(
            covered_a & {i for i, s in enumerate(at_a) if s < m.end and m.start < s + sizes_a[i]}
            for m in fact_check.mentions
        ):
            facts_reported += 1
    return {
        "reported": len(reported),
        "code_reported": code_reported,
        "reported_phantom": phantom,
        "unlocated": unlocated,
        "fact_changes_reported": facts_reported,
    }


def result_row(
    report: Report,
    audience: Audience,
    condition: Condition,
    backend: str,
    model: str,
    response: LlmResponse[Any],
) -> Row:
    """The fact guard of one version and, in `self_report`, the model's list against the diff."""
    row: Row = {
        "report": report.id,
        "source": report.source,
        "audience": audience,
        "condition": condition,
        "backend": backend,
        "model": model,
        "valid": response.value is not None,
        "words_report": len(report.text.split()),
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "latency_s": round(response.latency_s, 3),
    }
    if response.value is None:
        return row
    version = response.value.text
    found = diff(report.text, version)
    guard = check(
        report.text, version, language="pl", names=report.names, when=report.day, changes=found
    )
    row |= {
        "facts": len(guard.checks),
        "unchanged": guard.count("unchanged"),
        "changed": guard.count("changed"),
        "omitted": guard.count("omitted"),
        "new": len(guard.new),
        "words_version": len(version.split()),
        "code_changes": len(found.changes),
    }
    if condition == "self_report":
        listed = [c.model_dump() for c in response.value.changes]
        row |= self_report(report.text, version, found, guard, listed)
    return row


def execute(config: Rq6Config, reports: Sequence[Report], clients: Clients) -> list[Row]:
    """Edit every report for every audience with every backend in both conditions."""
    rows: list[Row] = []
    started = last = time.monotonic()
    total = len(reports) * len(config.audiences) * len(config.conditions) * len(clients.clients)
    done = 0
    for report in reports:
        for audience in config.audiences:
            seed = item_seed(config.base_seed, "rq6", report.id, audience)
            for name, client in clients.clients.items():
                for condition in config.conditions:
                    if name in clients.oracles:
                        backend = config.backend[name]
                        assert isinstance(backend, FakeBackend)
                        answer = oracle_answer(report, audience, condition, backend.error_rate)
                        clients.oracles[name].register(report.text, _fixed(answer))
                    call = redact_reporting if condition == "self_report" else redact
                    response = call(
                        client,
                        report.text,
                        audience,
                        language="pl",
                        seed=seed,
                        settings=config.redaction,
                    )
                    rows.append(
                        result_row(report, audience, condition, name, client.model, response)
                    )
                    done += 1
                    now = time.monotonic()
                    if now - last >= PROGRESS_INTERVAL_S or done == total:
                        print(
                            f"[{format_duration(now - started)}] {done}/{total} edits; last: "
                            f"{name} {report.id} {audience} {condition}",
                            flush=True,
                        )
                        last = now
    return rows


def write_csv(path: Path, rows: Sequence[Row]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: int(v) if isinstance(v, bool) else v for k, v in row.items()})


# --- Summaries ------------------------------------------------------------------------------


def _ratio(
    rows: Sequence[Row],
    numerator: str | Sequence[str],
    denominator: str | None,
    weights: FloatArray,
    ids: Mapping[str, int],
    scale: float = 100.0,
    digits: int = 1,
) -> str:
    """Σ numerator / Σ denominator over the rows (a row counts 1 without a denominator) with its
    cluster-bootstrap interval over reports, scaled."""
    names = [numerator] if isinstance(numerator, str) else list(numerator)
    size = weights.shape[1]
    top = np.zeros(size)
    bottom = np.zeros(size)
    for row in rows:
        cluster = ids[row["report"]]
        top[cluster] += sum(float(row[n] or 0) for n in names)
        bottom[cluster] += 1.0 if denominator is None else float(row[denominator] or 0)
    if bottom.sum() == 0:
        return "-"
    value = scale * top.sum() / bottom.sum()
    low, high = percentile_interval(resampled_ratio(weights, top, bottom))
    return f"{value:.{digits}f} [{scale * low:.{digits}f}, {scale * high:.{digits}f}]"


def _share_of(rows: Sequence[Row], test: str, weights: FloatArray, ids: Mapping[str, int]) -> str:
    """The share (in %) of rows whose `test` column is positive, with its interval."""
    flagged = [dict(r, _hit=1 if (r[test] or 0) > 0 else 0) for r in rows]
    return _ratio(flagged, "_hit", None, weights, ids)


def _groups(rows: Sequence[Row], condition: str) -> list[tuple[str, str, list[Row]]]:
    out = []
    for backend in dict.fromkeys(r["backend"] for r in rows):
        mine = [r for r in rows if r["backend"] == backend and r["condition"] == condition]
        for audience in dict.fromkeys(r["audience"] for r in mine):
            out.append((backend, audience, [r for r in mine if r["audience"] == audience]))
        if len({r["audience"] for r in mine}) > 1:
            out.append((backend, "all", mine))
    return out


def summary_markdown(run_id: str, rows: Sequence[Row], config: Rq6Config, own: int) -> str:
    """Per backend and audience (and over all audiences): the facts of the versions in both
    conditions, and the model's list of changes against the code diff."""
    reports = sorted({r["report"] for r in rows})
    ids = {report: i for i, report in enumerate(reports)}
    weights = resamples(len(reports), config.summary, "rq6")
    per_report = {r["report"]: int(r["facts"]) for r in rows if r["facts"] is not None}
    facts = sum(per_report.values())
    lines = [
        f"# RQ6 — editing reports for audiences — run {run_id}",
        "",
        f"{len(reports)} reports ({len(reports) - own} synthetic, generated from templates; {own} "
        f"added by hand), {facts} facts; audiences {', '.join(config.audiences)}. Shares and "
        "rates with 95 % cluster-bootstrap intervals over reports "
        f"({config.summary.bootstrap_resamples} resamples). A changed fact is the dangerous "
        "error; an omitted fact is reported, not an error.",
    ]
    for condition, title in (
        ("plain", "Facts in the edited versions (the application's prompt)"),
        ("self_report", "Facts when the model also lists its changes"),
    ):
        if condition not in config.conditions:
            continue
        lines += [
            "",
            f"## {title}",
            "",
            f"Condition {condition}",
            "",
            "| Backend | Audience | Valid | With a changed fact | Changed per 100 facts | "
            "With a new fact | New per version | Omitted per 100 facts | Length ratio |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for backend, audience, mine in _groups(rows, condition):
            valid = [r for r in mine if r["valid"]]
            lines.append(
                f"| {backend} | {audience} | {_share_of(mine, 'valid', weights, ids)} | "
                f"{_share_of(valid, 'changed', weights, ids)} | "
                f"{_ratio(valid, 'changed', 'facts', weights, ids)} | "
                f"{_share_of(valid, 'new', weights, ids)} | "
                f"{_ratio(valid, 'new', None, weights, ids, scale=1.0, digits=2)} | "
                f"{_ratio(valid, 'omitted', 'facts', weights, ids)} | "
                f"{_ratio(valid, 'words_version', 'words_report', weights, ids, 1.0, 2)} |"
            )
    if "self_report" in config.conditions:
        lines += [
            "",
            "## The model's own list of changes against the code diff",
            "",
            "Condition self_report",
            "",
            "| Backend | Audience | Diff changes per version | Listed per version | "
            "Diff changes listed | Listed not in the diff | Changed facts listed |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for backend, audience, mine in _groups(rows, "self_report"):
            valid = [r for r in mine if r["valid"]]
            lines.append(
                f"| {backend} | {audience} | "
                f"{_ratio(valid, 'code_changes', None, weights, ids, scale=1.0, digits=2)} | "
                f"{_ratio(valid, 'reported', None, weights, ids, scale=1.0, digits=2)} | "
                f"{_ratio(valid, 'code_reported', 'code_changes', weights, ids)} | "
                f"{_ratio(valid, ('reported_phantom', 'unlocated'), 'reported', weights, ids)} | "
                f"{_ratio(valid, 'fact_changes_reported', 'changed', weights, ids)} |"
            )
    tokens = sum(int(r["prompt_tokens"] or 0) + int(r["completion_tokens"] or 0) for r in rows)
    lines += ["", f"Tokens: {tokens} in {len(rows)} calls."]
    return "\n".join(lines) + "\n"


def latex_table(run_id: str, rows: Sequence[Row], config: Rq6Config) -> str:
    """Per backend over all audiences, condition plain: versions with a changed fact, changed,
    new and omitted facts, and the share of the diff's changes the model lists (booktabs)."""
    reports = sorted({r["report"] for r in rows})
    ids = {report: i for i, report in enumerate(reports)}
    weights = resamples(len(reports), config.summary, "rq6")
    lines = [
        f"% Generated by sentinel.experiments.rq6_study from run {run_id}; do not edit.",
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        "Backend & Audience & Changed (\\%) & Changed/100 & New/version & Omitted/100 & "
        "Listed (\\%) \\\\",
        "\\midrule",
    ]
    for backend, audience, mine in _groups(rows, "plain"):
        valid = [r for r in mine if r["valid"]]
        listed = [
            r
            for r in rows
            if r["valid"]
            and r["condition"] == "self_report"
            and r["backend"] == backend
            and (audience == "all" or r["audience"] == audience)
        ]
        cells = [
            _share_of(valid, "changed", weights, ids),
            _ratio(valid, "changed", "facts", weights, ids),
            _ratio(valid, "new", None, weights, ids, scale=1.0, digits=2),
            _ratio(valid, "omitted", "facts", weights, ids),
            _ratio(listed, "code_reported", "code_changes", weights, ids) if listed else "-",
        ]
        values = " & ".join(c.split(" [")[0] for c in cells)
        lines.append(f"{backend} & {audience} & {values} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


FIGURE_TITLES = {
    "en": ("With a changed fact (%)", "With a new fact (%)", "Omitted per 100 facts"),
    "pl": ("Ze zmienionym faktem (%)", "Z nowym faktem (%)", "Pominięte na 100 faktów"),
}
FIGURE_AUDIENCES = {
    "en": AUDIENCE_LABELS,
    "pl": {"edit": "Tylko redakcja", "board": "Zarząd", "finance": "Finanse", "team": "Zespół"},
}


def write_figure(
    folder: Path,
    rows: Sequence[Row],
    config: Rq6Config,
    *,
    language: str = "en",
    pdf_only: bool = False,
) -> list[str]:
    """Per audience and backend (condition plain): the share of versions with a changed fact,
    with a new fact, and the omitted facts per 100, with their intervals (PDF and PNG)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    titles, names_of = FIGURE_TITLES[language], FIGURE_AUDIENCES[language]
    reports = sorted({r["report"] for r in rows})
    ids = {report: i for i, report in enumerate(reports)}
    weights = resamples(len(reports), config.summary, "rq6")
    backends = list(dict.fromkeys(r["backend"] for r in rows))
    audiences = list(config.audiences)
    plt.rcParams.update({"font.size": 8, "svg.hashsalt": "rq6", "pdf.fonttype": 42})
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.4))
    width = 0.8 / max(1, len(backends))
    for k, column in enumerate(("changed", "new", "omitted")):
        ax = axes[k]
        for b, backend in enumerate(backends):
            values, lows, highs = [], [], []
            for audience in audiences:
                mine = [
                    r
                    for r in rows
                    if r["valid"]
                    and r["condition"] == "plain"
                    and r["backend"] == backend
                    and r["audience"] == audience
                ]
                cell = (
                    _ratio(mine, column, "facts", weights, ids)
                    if column == "omitted"
                    else _share_of(mine, column, weights, ids)
                )
                value, low, high = _parts(cell)
                values.append(value)
                lows.append(value - low)
                highs.append(high - value)
            xs = np.arange(len(audiences)) + (b - (len(backends) - 1) / 2) * width
            ax.bar(xs, values, width, yerr=[lows, highs], capsize=2, label=backend)
        ax.set_xticks(np.arange(len(audiences)))
        ax.set_xticklabels([names_of.get(a, a) for a in audiences], rotation=20)
        ax.set_title(titles[k])
        ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False)
    figure.tight_layout()
    names = []
    for suffix in ("pdf",) if pdf_only else ("pdf", "png"):
        name = f"{FIGURE}.{suffix}"
        metadata = {"CreationDate": None} if suffix == "pdf" else {"Software": None}
        figure.savefig(folder / name, dpi=200, metadata=metadata)
        names.append(name)
    plt.close(figure)
    return names


def _parts(cell: str) -> tuple[float, float, float]:
    if cell == "-":
        return 0.0, 0.0, 0.0
    match = re.match(r"([\d.]+) \[([\d.]+|nan), ([\d.]+|nan)\]", cell)
    assert match, cell
    value = float(match[1])
    low = float(match[2]) if match[2] != "nan" else value
    high = float(match[3]) if match[3] != "nan" else value
    return value, low, high


def write_summaries(
    run_dir: Path, run_id: str, rows: Sequence[Row], config: Rq6Config, own: int
) -> list[str]:
    table = f"{config.summary.table}.tex"
    (run_dir / SUMMARY_FILE).write_text(
        summary_markdown(run_id, rows, config, own), encoding="utf-8"
    )
    (run_dir / table).write_text(latex_table(run_id, rows, config), encoding="utf-8")
    return [SUMMARY_FILE, table, *write_figure(run_dir, rows, config)]


def prompt_records(config: Rq6Config) -> dict[str, dict[str, str]]:
    """The version and SHA-256 of every prompt file the run's calls use."""
    version = config.redaction.prompt_version
    names = [REDACT_PROMPT, FORMAT_PROMPT, FORMAT_CHANGES_PROMPT]
    names += [STYLE_PROMPT.format(audience=a) for a in config.audiences]
    return {
        name: {"version": version, "sha256": load_prompt(name, version).sha256} for name in names
    }


def run(args: Any, command: str) -> Path:
    """Edit every report with the selected backends; write the run directory."""
    raw = runs.load_toml(args.config)
    config = Rq6Config.model_validate(raw)
    selected = config.selected(args.backend)
    reports, own = load_reports(config, args.limit)
    corpus_hash = hashlib.sha256(config.corpus.read_bytes()).hexdigest()
    started = datetime.now(UTC)
    git = runs.git_state()  # taken before any output of the run exists
    digest = runs.config_hash(raw, args.limit, {"backends": selected, "corpus": corpus_hash})
    run_id = runs.make_run_id(started, digest)
    clients = open_clients(config, selected, args.cache_mode, args.cache_file, args.replay)
    calls = len(reports) * len(config.audiences) * len(config.conditions) * len(selected)
    print(
        f"run {run_id}: {len(reports)} reports x {len(config.audiences)} audiences x "
        f"{len(config.conditions)} conditions x {len(selected)} backends = {calls} edits",
        flush=True,
    )
    rows = execute(config, reports, clients)
    run_dir = runs.create_run_dir(args.out, run_id, smoke=args.limit is not None)
    write_csv(run_dir / RESULTS_FILE, rows)
    bundle = (0, 0) if own else write_run_bundle(run_dir, clients)
    outputs = [RESULTS_FILE, *write_summaries(run_dir, run_id, rows, config, own)]
    if not own:
        outputs.append(BUNDLE_FILE)
    data = manifest(
        run_id=run_id,
        started=started,
        git=git,
        command=command,
        config_path=args.config,
        raw_config=raw,
        digest=digest,
        limit=args.limit,
        selected=selected,
        clients=clients,
        cache_file=args.cache_file,
        bundle=bundle,
        outputs=outputs,
        extra={
            "corpus": {"path": str(config.corpus), "sha256": corpus_hash, "synthetic": True},
            "own_reports": own,
            "prompts": prompt_records(config),
            "seeds": {"base_seed": config.base_seed},
            "seed_rule": SEED_RULE,
            "n_reports": len(reports),
            "n_rows": len(rows),
        },
    )
    runs.write_json(run_dir / "manifest.json", data)
    return run_dir


def regenerate(run_dir: Path) -> list[str]:
    """Regenerate summary.md, the LaTeX table and the figure of a run from its manifest and
    results.csv (`sentinel reproduce --check`; no edit is checked again)."""
    recorded = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = Rq6Config.model_validate(recorded["config"])
    rows = read_rows(run_dir / RESULTS_FILE)
    return write_summaries(run_dir, recorded["run_id"], rows, config, int(recorded["own_reports"]))


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status (3: stopped by a rate limit)."""
    return run_main(
        "sentinel.experiments.rq6_study",
        "RQ6: does AI editing for audiences preserve the facts?",
        argv,
        run,
    )


if __name__ == "__main__":
    sys.exit(main())
