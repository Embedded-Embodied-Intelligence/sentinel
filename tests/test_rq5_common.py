"""What the RQ5 runners share (WP6c): exit status 3 with the right hint after a rate-limit or a
credits stop, `--replay` of one backend from a file while the others use their cache, and caches
without prompts when the config says so. No data and no network."""

import argparse
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from sentinel.experiments.rq5_common import EXIT_QUOTA, LlmStudyConfig, open_clients, run_main
from sentinel.llm import (
    CacheMiss,
    CreditsExhausted,
    FakeLlmClient,
    LlmCache,
    LlmError,
    Message,
    QuotaExhausted,
)
from sentinel.llm.cache import write_bundle


class Count(BaseModel):
    a: int


def study_config(tmp_path: Path, *, store_prompts: bool) -> LlmStudyConfig:
    return LlmStudyConfig.model_validate(
        {
            "name": "test",
            "base_seed": 1,
            "cache_dir": str(tmp_path / "cache"),
            "store_prompts": store_prompts,
            "backends": ["fake", "other"],
            "backend": {"fake": {"kind": "fake"}, "other": {"kind": "fake", "model": "other"}},
            "summary": {"table": "table_test"},
        }
    )


def test_a_credits_or_rate_limit_stop_exits_with_status_3_and_its_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def stopping(error: LlmError) -> Callable[[argparse.Namespace, str], Path]:
        def run(args: argparse.Namespace, command: str) -> Path:
            raise error

        return run

    argv = ["--config", "study.toml", "--out", str(tmp_path)]
    no_credits = CreditsExhausted("OpenRouter request failed: HTTP 402: Insufficient credits")
    assert run_main("study", "test", argv, stopping(no_credits)) == EXIT_QUOTA
    message = capsys.readouterr().err
    assert "HTTP 402" in message and "add credits" in message and "no run directory" in message
    limited = QuotaExhausted("Groq request failed: HTTP 429", 7200.0)
    assert run_main("study", "test", argv, stopping(limited)) == EXIT_QUOTA
    assert "run the same command again in about 2.0 h" in capsys.readouterr().err

    seen: dict[str, object] = {}

    def record(args: argparse.Namespace, command: str) -> Path:
        seen["replay"] = args.replay
        return tmp_path

    assert run_main("study", "test", [*argv, "--replay", "ollama=bundle.gz"], record) == 0
    assert seen["replay"] == {"ollama": Path("bundle.gz")}
    for wrong in (["--replay", "ollama"], ["--replay", "a=x", "--cache-file", "x"]):
        with pytest.raises(SystemExit):
            run_main("study", "test", [*argv, *wrong], record)


def test_one_backend_replays_from_a_file_and_no_cache_holds_the_messages(
    tmp_path: Path,
) -> None:
    messages = [Message(role="user", content="Ewa Lis is off sick until Monday.")]
    recorder = FakeLlmClient(
        ['{"a": 1}'], model="oracle", cache=LlmCache(tmp_path / "rec.jsonl", store_prompts=False)
    )
    recorder.complete(messages, schema=Count, seed=1, max_tokens=8)
    assert recorder.cache is not None
    bundle = tmp_path / "bundle.jsonl.gz"
    write_bundle(bundle, recorder.cache.used.values())

    config = study_config(tmp_path, store_prompts=False)
    clients = open_clients(config, ["fake", "other"], "auto", None, {"fake": bundle})
    fake, other = clients.clients["fake"], clients.clients["other"]
    assert (fake.mode, other.mode, clients.mode, clients.replay) == (
        "replay",
        "auto",
        "auto",
        {"fake": bundle},
    )
    assert fake.complete(messages, schema=Count, seed=1, max_tokens=8).cache_hit
    with pytest.raises(CacheMiss):  # replay: a miss is an error, never a backend call
        fake.complete(messages, schema=Count, seed=2, max_tokens=8)
    clients.oracles["other"].register(messages[0].content, lambda _: '{"a": 2}')
    assert other.complete(messages, schema=Count, seed=1, max_tokens=8).value == Count(a=2)
    stored = (tmp_path / "cache" / "other.jsonl").read_text(encoding="utf-8")
    assert "Ewa" not in stored and '"store_prompts":false' in stored
    assert all(cache is not None and not cache.store_prompts for cache in clients.caches.values())
