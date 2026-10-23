"""The RQ5 study runners of WP6b on the scripted oracle (they need the PSPLIB data): every output,
replay from the bundle, and the decision-state recorder's sample written into its config."""

import csv
import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from sentinel.experiments import event_study, explanation_study, online_study, proposal_study
from sentinel.experiments.decision_states import StatesConfig
from sentinel.experiments.runs import load_toml

REPO_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.data


def local_config(name: str, tmp_path: Path, **replace: str) -> Path:
    """A copy of configs/<name> with its LLM cache (and other settings) under `tmp_path`."""
    text = (REPO_ROOT / "configs" / name).read_text(encoding="utf-8")
    text = text.replace('"data/llm_cache/rq5"', f'"{tmp_path / "cache"}"')
    for old, new in replace.items():
        text = re.sub(old, new, text, flags=re.MULTILINE)
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def run_dir(out: Path) -> Path:
    found = sorted(out.iterdir())
    assert len(found) == 1
    return found[0]


def test_the_event_study_writes_every_output_and_replays_from_its_bundle(
    psplib_root: Path, tmp_path: Path
) -> None:
    config = local_config("wp6_rq5_events.toml", tmp_path)
    out = tmp_path / "out"
    args = ["--config", str(config), "--out", str(out), "--backend", "fake", "--limit", "1"]
    assert event_study.main(args) == 0
    first = run_dir(out)
    for name in ("results.csv", "messages.jsonl", "summary.md", "manifest.json"):
        assert (first / name).is_file()
    with (first / "results.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2 * 5 and {r["condition"] for r in rows} == {"single_shot", "repair"}
    assert all(r["leaks"] == "0" for r in rows)
    replay = tmp_path / "replay"
    bundle = first / "llm_cache.jsonl.gz"
    assert (
        event_study.main([*args[:2], "--out", str(replay), *args[4:], "--cache-file", str(bundle)])
        == 0
    )
    assert (run_dir(replay) / "results.csv").read_bytes() == (first / "results.csv").read_bytes()


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "record_decision_states", REPO_ROOT / "scripts" / "record_decision_states.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.slow
def test_recorded_states_feed_the_proposal_explanation_and_online_studies(
    psplib_root: Path, tmp_path: Path
) -> None:
    states = local_config(
        "wp6_rq5_states.toml",
        tmp_path,
        **{
            r"^states_dir = .*$": f'states_dir = "{tmp_path / "states"}"',
            r"^stride = 8 .*$": "stride = 480",
            r"^lambda_a = .*$": "lambda_a = [0.01]",
            r"^size = 150$": "size = 4",
            r"^max_workers = .*$": "max_workers = 1",
        },
    )
    assert load_script().main(["--config", str(states), "--write-sample"]) == 0
    ids = StatesConfig.model_validate(load_toml(states)).sample.ids
    assert len(ids) == 4 and all(i.startswith("j30/j301_1/la0.01/r0/") for i in ids)
    replace = {r"^states = .*$": f'states = "{states}"'}
    for module, name in (
        (proposal_study, "wp6_rq5_proposals.toml"),
        (explanation_study, "wp6_rq5_explanations.toml"),
    ):
        config = local_config(name, tmp_path, **replace)
        out = tmp_path / f"out-{module.__name__.rsplit('.', 1)[-1]}"
        args = ["--config", str(config), "--out", str(out), "--backend", "fake", "--limit", "2"]
        assert module.main(args) == 0
        produced = run_dir(out)
        assert (produced / "summary.md").is_file() and (produced / "llm_cache.jsonl.gz").is_file()
        with (produced / "results.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        sources = {r.get("source") or r.get("backend") for r in rows}
        assert sources == ({"fake", "random"} if module is proposal_study else {"fake"})
    online = local_config("wp6_rq5_online.toml", tmp_path, **replace)
    out = tmp_path / "online"
    args = ["--config", str(online), "--out", str(out), "--backend", "fake", "--limit", "1"]
    assert online_study.main(args) == 0
    with (run_dir(out) / "results.csv").open(encoding="utf-8") as handle:
        (row,) = list(csv.DictReader(handle))
    assert row["instance"] == "j301_1" and int(row["calls"]) == int(row["gated"]) > 0
    assert row["wp5_makespan"]
