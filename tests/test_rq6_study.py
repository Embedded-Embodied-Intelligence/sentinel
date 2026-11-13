"""RQ6 (WP20): the corpus matches the fact guard, the runner measures facts and the model's
list of changes, and its summaries and paper artifacts regenerate byte for byte (slow)."""

import json
import shutil
from pathlib import Path

import pytest

from sentinel.experiments import paper_rq6, rq6_study
from sentinel.experiments.report_corpus import check_report, load_corpus
from sentinel.experiments.reproduce import check_rq6, check_run
from sentinel.interpret.facts import check
from sentinel.interpret.tracked import diff

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
