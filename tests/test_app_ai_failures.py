"""When the AI fails (WP11; the live runs): limits for a person waiting, failures in plain words
and a retry that reaches the model."""

import socket
from pathlib import Path

import pytest

from sentinel.app.errors import AppError
from sentinel.app.llm import OLLAMA_TIMEOUT_S, LlmSettings, RequestCache, failure, make_client
from sentinel.llm import (
    LlmCache,
    LlmError,
    Message,
    OllamaClient,
    OpenRouterClient,
    QuotaExhausted,
    RequestTooLarge,
)
from sentinel.llm.core import Reply, Request
from sentinel.llm.http import TransportError, TransportTimeout, urllib_transport


def _request(text: str) -> Request:
    return Request(
        backend="ollama",
        model="m",
        digest=None,
        messages=(Message(role="user", content=text),),
        schema_name="Extraction",
        json_schema={},
        temperature=0.0,
        seed=1,
        max_tokens=10,
    )


def _reply(meta: dict[str, object] | None = None) -> Reply:
    return Reply(
        text="{}", model="m", prompt_tokens=1, completion_tokens=1, latency_s=0.1, meta=meta or {}
    )  # type: ignore[arg-type]


def test_an_invalid_answer_is_known_only_to_the_request_that_got_it(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    first = RequestCache(path, store_prompts=False)
    bad, good = _request("bad"), _request("good")
    first.put(bad, _reply({"withheld": {"kind": "json", "message": "not JSON", "details": []}}))
    first.put(good, _reply())
    assert first.get(bad.key) is not None  # its repair rounds replay it
    later = RequestCache(path, store_prompts=False)
    assert later.get(bad.key) is None and later.get(good.key) is not None
    # A study's cache replays every answer as it was recorded.
    assert LlmCache(path, store_prompts=False).get(bad.key) is not None


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (LlmError("no", status=401), "llm_key"),
        (LlmError("no", status=403), "llm_key"),
        (LlmError("no", status=404), "llm_model"),
        (LlmError("no", status=400), "llm_model"),
        (LlmError("no", status=500), "llm_failed"),
        (LlmError("not JSON"), "llm_failed"),
        (TransportError("refused"), "llm_unreachable"),
        (TransportTimeout("slow"), "llm_timeout"),
        (QuotaExhausted("wait", 3600.0), "llm_quota"),
        (RequestTooLarge("long"), "llm_too_long"),
    ],
)
def test_a_failed_call_says_what_went_wrong(error: LlmError, code: str) -> None:
    found = failure(error)
    assert isinstance(found, AppError) and found.code == code and found.kind == "unavailable"


def test_a_person_waits_less_for_an_answer_than_a_study(tmp_path: Path) -> None:
    cache = LlmCache(tmp_path / "c.jsonl", store_prompts=False)
    local = make_client(LlmSettings(provider="ollama"), cache)
    assert isinstance(local, OllamaClient) and local.timeout_s == OLLAMA_TIMEOUT_S
    settings = LlmSettings(provider="openrouter", api_key="k")  # pragma: allowlist secret
    cloud = make_client(settings, cache)
    assert isinstance(cloud, OpenRouterClient) and cloud.timeout_s < 300 and cloud.max_retries < 6
    set_by_config = make_client(LlmSettings(provider="ollama"), cache, timeout_s=3.0)
    assert isinstance(set_by_config, OllamaClient) and set_by_config.timeout_s == 3.0


def test_a_wrong_address_and_a_silent_server_are_transport_errors() -> None:
    for address in ("not a url", "localhost:11434/api", "http://"):
        with pytest.raises(TransportError):
            urllib_transport("GET", address, body=None, headers={}, timeout=0.2)
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        url = f"http://127.0.0.1:{silent.getsockname()[1]}/"
        with pytest.raises(TransportTimeout):
            urllib_transport("GET", url, body=None, headers={}, timeout=0.05)
