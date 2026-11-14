"""RQ6 (WP20): the corpus matches the fact guard, the runner measures facts and the model's
list of changes, records a failed edit as a model error and goes on, and its summaries and
paper artifacts regenerate byte for byte (slow)."""

import json
import shutil
from pathlib import Path

import pytest

from sentinel.experiments import paper_rq6, rq6_study
from sentinel.experiments.report_corpus import Report, check_report, load_corpus
from sentinel.experiments.reproduce import check_rq6, check_run
from sentinel.experiments.rq5_common import EXIT_QUOTA, Answer
from sentinel.interpret.facts import check
from sentinel.interpret.tracked import diff
from sentinel.llm import CacheMiss, LlmError, QuotaExhausted, RequestTooLarge
from sentinel.llm.http import TransportError, TransportTimeout

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs" / "wp20_rq6.toml"
CORPUS = REPO_ROOT / "configs" / "wp20_rq6_corpus.json"


def test_the_corpus_is_synthetic_and_the_guard_finds_exactly_its_facts() -> None:
    reports = load_corpus(CORPUS)
    assert len(reports) == 30 and {r.source for r in reports} == {"showcase", "simulator"}
    assert [issue for r in reports[::10] for issue in check_report(r)] == []
    kinds = {f.kind for r in reports for f in r.facts}
    assert kinds == {"amount", "date", "number", "percent", "person", "project", "task"}


@pytest.mark.slow
def test_the_guard_finds_exactly_the_facts_of_every_report() -> None:
    assert [issue for r in load_corpus(CORPUS) for issue in check_report(r)] == []


def test_the_model_s_list_is_compared_with_the_code_diff() -> None:
    (report, *_) = load_corpus(CORPUS)
    version = report.text.replace("Ogólnie rzecz biorąc", "Krótko mówiąc", 1)
    first_days = report.text.split(" dni")[0].rsplit(" ", 1)[-1]
    version = version.replace(f" {first_days} dni", f" {int(first_days) + 1} dni", 1)
    found = diff(report.text, version)
    guard = check(report.text, version, names=report.names, when=report.day, changes=found)
    listed = [
        {"before": "Ogólnie rzecz biorąc", "after": "Krótko mówiąc"},
        {"before": "x y z", "after": ""},
    ]
    measured = rq6_study.self_report(report.text, version, found, guard, listed)
    assert len(found.changes) == 2 and guard.count("changed") == 1
    assert measured == {
        "reported": 2,
        "code_reported": 1,
        "reported_phantom": 0,
        "unlocated": 1,
        "fact_changes_reported": 0,
    }


def _run(tmp_path: Path, limit: int | None) -> Path:
    config = tmp_path / "wp20_rq6.toml"
    text = CONFIG.read_text(encoding="utf-8")
    text = text.replace('corpus = "configs/', f'corpus = "{REPO_ROOT.as_posix()}/configs/')
    text = text.replace(
        'cache_dir = "data/llm_cache/rq6"', f'cache_dir = "{(tmp_path / "cache").as_posix()}"'
    )
    config.write_text(text, encoding="utf-8")
    args = ["--config", str(config), "--out", str(tmp_path / "out"), "--backend", "fake"]
    assert rq6_study.main([*args, *(["--limit", str(limit)] if limit else [])]) == 0
    (run_dir,) = (tmp_path / "out").iterdir()
    return run_dir


@pytest.mark.slow
def test_a_smoke_run_writes_rows_summaries_and_a_bundle(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, 2)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["smoke"] and manifest["n_rows"] == 2 * 4 * 2 and manifest["own_reports"] == 0
    rows = (
        rq6_study.read_rows(run_dir / rq6_study.RESULTS_FILE)
        if hasattr(rq6_study, "read_rows")
        else None
    )
    assert all(r["facts"] in (32, 33) for r in rows)
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "Diff changes listed" in summary and "| fake | all |" in summary
    assert {"fig_rq6.pdf", "fig_rq6.png", "llm_cache.jsonl.gz"} <= {
        p.name for p in run_dir.iterdir()
    }
    count, bad = check_run(run_dir, tmp_path / "scratch")
    assert count == 4 and bad == []


@pytest.mark.slow
def test_a_pinned_full_run_generates_paper_artifacts_that_regenerate(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, None)
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**manifest, "smoke": False, "git_dirty": False}), encoding="utf-8")
    config = tmp_path / "paper_rq6.toml"
    paper_rq6.pin(run_dir, config, out_dir=(tmp_path / "generated").as_posix())
    written = paper_rq6.generate(config)
    names = sorted(p.relative_to(tmp_path / "generated").as_posix() for p in written)
    assert names == [
        "MANIFEST.json",
        "fig_rq6.pdf",
        "numbers.tex",
        "pl/fig_rq6.pdf",
        "pl/numbers.tex",
        "pl/tab_rq6.tex",
        "tab_rq6.tex",
    ]
    numbers = (tmp_path / "generated" / "numbers.tex").read_text(encoding="utf-8")
    assert r"\newcommand{\RQsixReports}{30}" in numbers and "RQsixDiffListedFakeAll" not in numbers
    files, wrong = check_rq6(config, tmp_path / "check")
    assert wrong == 0 and files == 4 + 7
    shutil.rmtree(tmp_path / "cache")


def test_an_error_kind_is_a_short_code_without_the_message() -> None:
    kinds = [
        rq6_study.error_kind(exc)
        for exc in (
            LlmError('Ollama /api/chat returned HTTP 500: {"error":"aborted"}', status=500),
            LlmError("Ollama /api/chat returned dict, expected an object"),
            CacheMiss("ollama request 0123456789ab is not in the cache (replay)"),
            RequestTooLarge("too large"),
            TransportTimeout("POST /api/chat failed: timed out"),
            TransportError("POST /api/chat failed: refused"),
        )
    ]
    assert kinds == ["http_500", "backend", "cache_miss", "too_large", "timeout", "transport"]


LOOP = "the backend loops"  # a scripted answer that fails as Ollama's repeat limit does


def _failing(monkeypatch: pytest.MonkeyPatch, error: LlmError) -> None:
    """The scripted editor raises `error` for Zarząd in plain and answers Zespół in
    self_report against the schema (an empty text, no list); every other edit as scripted."""
    scripted, fixed = rq6_study.oracle_answer, rq6_study._fixed

    def answer(report: Report, audience: str, condition: str, rate: float) -> str:
        if (audience, condition) == ("board", "plain"):
            return LOOP
        if (audience, condition) == ("team", "self_report"):
            return json.dumps({"text": ""})
        return scripted(report, audience, condition, rate)  # type: ignore[arg-type]

    def respond(text: str) -> Answer:
        def loop(round_index: int) -> str:
            raise error

        return loop if text == LOOP else fixed(text)

    monkeypatch.setattr(rq6_study, "oracle_answer", answer)
    monkeypatch.setattr(rq6_study, "_fixed", respond)


def test_a_failed_edit_is_a_model_error_and_the_run_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    message = 'Ollama /api/chat returned HTTP 500: {"error":"token repeat limit reached"}'
    _failing(monkeypatch, LlmError(message, status=500))
    run_dir = _run(tmp_path, 1)
    rows = rq6_study.read_rows(run_dir / rq6_study.RESULTS_FILE)
    assert len(rows) == 4 * 2
    failed = {(r["audience"], r["condition"]): r["error"] for r in rows if r["outcome"] != "ok"}
    assert failed == {("board", "plain"): "http_500", ("team", "self_report"): "schema"}
    assert {r["outcome"] for r in rows} == {"ok", "model_error"}
    assert all(r["facts"] is None and r["changed"] is None for r in rows if r["error"])
    assert all(r["facts"] in (32, 33) and r["error"] is None for r in rows if not r["error"])
    assert "repeat" not in (run_dir / rq6_study.RESULTS_FILE).read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n_rows"] == 8 and manifest["n_model_errors"] == 2
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "| fake | plain | 4 | 25.0 [25.0, 25.0] | 3 | http_500: 1 |" in summary
    assert "| fake | self_report | 4 | 25.0 [25.0, 25.0] | 3 | schema: 1 |" in summary
    assert "| fake | board | 1 | 100.0 [100.0, 100.0] | 0 | - | - | - | - | - | - |" in summary
    assert "| fake | all | 4 | 25.0 [25.0, 25.0] | 3 | " in summary
    assert "| fake | team | 0 | - | - | - | - | - |" in summary
    assert "Tokens: " in summary and "in 8 edits (2 model errors)." in summary
    table = (run_dir / "table_wp20_rq6.tex").read_text(encoding="utf-8")
    assert "fake & board & 0 & 100.0 & - & - & - & - & 1 & 0.0 &" in table
    assert "fake & all & 3 & 25.0 &" in table
    count, bad = check_run(run_dir, tmp_path / "scratch")
    assert count == 4 and bad == []


def test_a_rate_limit_still_stops_the_run_to_resume_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _failing(monkeypatch, QuotaExhausted("rate limit: retry in 2 h", retry_after_s=7200.0))
    config = tmp_path / "wp20_rq6.toml"
    text = CONFIG.read_text(encoding="utf-8")
    text = text.replace('corpus = "configs/', f'corpus = "{REPO_ROOT.as_posix()}/configs/')
    text = text.replace(
        'cache_dir = "data/llm_cache/rq6"', f'cache_dir = "{(tmp_path / "cache").as_posix()}"'
    )
    config.write_text(text, encoding="utf-8")
    args = ["--config", str(config), "--out", str(tmp_path / "out"), "--backend", "fake"]
    assert rq6_study.main([*args, "--limit", "1"]) == EXIT_QUOTA
    assert not (tmp_path / "out").exists()
    assert "model error" not in capsys.readouterr().out


@pytest.mark.slow
def test_paper_artifacts_of_a_run_with_model_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _failing(monkeypatch, LlmError("Ollama /api/chat returned HTTP 500: loop", status=500))
    run_dir = _run(tmp_path, 1)
    results = run_dir / rq6_study.RESULTS_FILE  # the paper names Qwen, not the scripted editor
    results.write_text(
        results.read_text(encoding="utf-8").replace(",fake,", ",ollama,"), encoding="utf-8"
    )
    rq6_study.regenerate(run_dir)
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**manifest, "smoke": False, "git_dirty": False}), encoding="utf-8")
    config = tmp_path / "paper_rq6.toml"
    paper_rq6.pin(run_dir, config, out_dir=(tmp_path / "generated").as_posix())
    paper_rq6.generate(config)
    numbers = (tmp_path / "generated" / "numbers.tex").read_text(encoding="utf-8")
    assert r"\newcommand{\RQsixErrorsQwenBoard}{100.0}" in numbers
    assert r"\newcommand{\RQsixSuccessfulQwenBoard}{0}" in numbers
    assert r"\newcommand{\RQsixSelfErrorsQwenTeam}{100.0}" in numbers
    assert r"\newcommand{\RQsixErrorsQwenAll}{25.0}" in numbers
    assert "RQsixChangedVersionsQwenBoard" not in numbers
    assert "RQsixDiffListedQwenTeam" not in numbers and "RQsixDiffListedQwenAll" in numbers
    table = (tmp_path / "generated" / "tab_rq6.tex").read_text(encoding="utf-8")
    assert r"qwen2.5:7b & Board & 0 & 100.0 & -- & -- & -- & -- & 1 & 0.0 &" in table
    files, wrong = check_rq6(config, tmp_path / "check")
    assert wrong == 0 and files == 4 + 7
