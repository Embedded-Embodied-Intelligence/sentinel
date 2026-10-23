"""RQ1 study runner (WP6a): the config follows the study plan; a run on the scripted oracle
writes every output, its replay bundle reproduces it without a backend, a rate-limit stop
writes nothing and resumes from the cache, and the summaries regenerate identically."""

import csv
import json
import shutil
import tomllib
from pathlib import Path

import pytest

from sentinel import cli
from sentinel.experiments import wbs_study
from sentinel.experiments.wbs_config import GroqBackend, OllamaBackend, WbsStudyConfig
from sentinel.llm import FakeLlmClient, QuotaExhausted, Reply, Request
from sentinel.wbs.narrate import parse_narration

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = """
name = "fake_wp6"
base_seed = 7
narrator_seed = 8
data_root = "{root}"
cache_dir = "{cache}"
styles = ["structured", "narrative"]
backends = ["fake"]

[[sets]]
name = "tiny"

[extraction]
max_tokens = 512

[cpsat]
deterministic_time_limit = 1.0

[backend.fake]
kind = "fake"
max_faulty_rounds = 2

[summary]
bootstrap_resamples = 50
"""


def write_study(folder: Path, tiny_path: Path) -> Path:
    """A config over a set `tiny` of two copies of the tiny fixture, on the fake backend."""
    root = folder / "psplib"
    (root / "tiny").mkdir(parents=True)
    for stem in ("tiny1_1", "tiny1_2"):
        shutil.copy(tiny_path, root / "tiny" / f"{stem}.sm")
    config = folder / "wbs.toml"
    text = CONFIG.format(root=root.as_posix(), cache=(folder / "cache").as_posix())
    config.write_text(text, encoding="utf-8")
    return config


@pytest.fixture
def study(tmp_path: Path, tiny_path: Path) -> Path:
    return write_study(tmp_path, tiny_path)


@pytest.fixture(scope="module")
def fake_run(tmp_path_factory: pytest.TempPathFactory, tiny_path: Path) -> tuple[Path, Path]:
    """One run on the oracle and its replay from the bundle, shared by the tests below."""
    folder = tmp_path_factory.mktemp("wbs")
    config = write_study(folder, tiny_path)
    run_dir = run(config, folder / "results")
    return run_dir, run(config, folder / "replay", cache_file=run_dir / "llm_cache.jsonl.gz")


def run(config: Path, out: Path, **settings: object) -> Path:
    arguments: dict[str, object] = {
        "limit": None,
        "backends": [],
        "cache_mode": "auto",
        "cache_file": None,
        "command": "test",
    }
    arguments.update(settings)
    return wbs_study.run_study(config, out, **arguments)  # type: ignore[arg-type]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_the_rq1_config_follows_the_study_plan() -> None:
    """docs/experiments/plan.md (RQ1): J30 every 12th, both styles, Ollama qwen2.5:7b with its
    weights pinned and Groq gpt-oss-120b on the free plan, up to 3 repair rounds."""
    raw = tomllib.loads((REPO_ROOT / "configs" / "wp6_rq1.toml").read_text(encoding="utf-8"))
    config = WbsStudyConfig.model_validate(raw)
    assert [(s.name, s.stride) for s in config.sets] == [("j30", 12)]
    assert config.styles == ("structured", "narrative") and config.backends == ("ollama", "groq")
    ollama, groq = config.backend["ollama"], config.backend["groq"]
    assert isinstance(ollama, OllamaBackend) and isinstance(groq, GroqBackend)
    assert ollama.model == "qwen2.5:7b" and ollama.digest is not None
    assert (groq.model, groq.tokens_per_minute, groq.tokens_per_day) == (
        "openai/gpt-oss-120b",
        8000,
        200000,
    )
    extraction = config.extraction
    assert (extraction.prompt_version, extraction.temperature) == ("v1", 0.0)
    assert extraction.max_repair_rounds == 3
    assert config.cpsat.deterministic_time_limit == 5.0 and config.cpsat.num_workers == 1


def test_a_fake_run_writes_every_output_and_its_bundle_replays_it(
    fake_run: tuple[Path, Path],
) -> None:
    run_dir, replay = fake_run
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for name in manifest["outputs"]:
        assert (run_dir / name).is_file(), name
    assert {"summary.md", "table_wp6_rq1.tex", "fig_wp6_rq1.pdf", "fig_wp6_rq1.png"} <= set(
        manifest["outputs"]
    )
    results = rows(run_dir / "results.csv")
    assert len(results) == 2 * 2 * 2 and manifest["n_rows"] == 8
    assert {(r["condition"], r["style"]) for r in results} == {
        (c, s) for c in ("single_shot", "repair") for s in ("structured", "narrative")
    }
    assert len(rows(run_dir / "rounds.csv")) == 2 * 2 * 4
    repaired = [r for r in results if r["condition"] == "repair"]
    assert all(r["valid"] == "1" and r["exact"] == "1" for r in repaired)
    assert all(r["makespan_extracted"] == r["makespan_true"] == "7" for r in repaired)
    assert manifest["cache_hit_rate"] == 0.0 and manifest["llm"]["fake"]["stats"]["calls"] > 4
    assert manifest["bundle"]["entries"] == manifest["llm"]["fake"]["stats"]["calls"]

    for name in ("results.csv", "rounds.csv", "llm_cache.jsonl.gz"):
        assert (replay / name).read_bytes() == (run_dir / name).read_bytes(), name
    replayed = json.loads((replay / "manifest.json").read_text(encoding="utf-8"))
    assert replayed["cache_hit_rate"] == 1.0 and replayed["cache_mode"] == "replay"


def test_a_rate_limit_stop_writes_nothing_and_the_rerun_resumes_from_the_cache(
    study: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    send = FakeLlmClient._send
    calls = []

    def limited(self: FakeLlmClient, request: Request) -> Reply:
        if len(calls) == 3:
            raise QuotaExhausted("rate limit: retry after 7200 s", 7200.0)
        calls.append(request.key)
        return send(self, request)

    monkeypatch.setattr(FakeLlmClient, "_send", limited)
    out = tmp_path / "results"
    argv = ["--config", str(study), "--out", str(out), "--backend", "fake"]
    assert wbs_study.main(argv) == wbs_study.EXIT_QUOTA
    assert "about 2.0 h to resume" in capsys.readouterr().err
    assert not out.exists() or not any(out.iterdir())
    monkeypatch.setattr(FakeLlmClient, "_send", send)
    assert wbs_study.main(argv) == 0
    (run_dir,) = out.iterdir()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm"]["fake"]["stats"]["cache_hits"] == 3


def test_the_summaries_regenerate_identically(fake_run: tuple[Path, Path]) -> None:
    run_dir = fake_run[1]
    before = {n: (run_dir / n).read_bytes() for n in ("summary.md", "table_wp6_rq1.tex")}
    figure = (run_dir / "fig_wp6_rq1.pdf").read_bytes()
    assert cli.main(["summarise-wbs", str(run_dir)]) == 0
    assert {n: (run_dir / n).read_bytes() for n in before} == before
    assert (run_dir / "fig_wp6_rq1.pdf").read_bytes() == figure
    summary = json.loads((run_dir / "summary_manifest.json").read_text(encoding="utf-8"))
    assert summary["generator"] == "sentinel.experiments.wbs_summary"
    assert [i["path"] for i in summary["inputs"]][:2] == ["results.csv", "rounds.csv"]


def test_the_oracle_is_faulty_for_its_first_rounds_then_right(tiny_path: Path) -> None:
    from sentinel.data.psplib_loader import load_psplib
    from sentinel.wbs.extract import validate_extraction
    from sentinel.wbs.narrate import narrate

    text = narrate(load_psplib(tiny_path), style="narrative", seed=3)
    oracle = wbs_study.OracleResponder(max_faulty_rounds=4, seed=1)
    answers = [oracle.answer(text, i) for i in range(6)]
    faulty = [bool(validate_extraction(a)) for a in answers]
    assert faulty == sorted(faulty, reverse=True) and not faulty[-1]
    assert answers[-1] == json.loads(parse_narration(text).model_dump_json())
