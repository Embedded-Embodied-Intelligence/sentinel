"""LLM layer (WP6a, WP6c): record/replay cache (also without prompts), schema violations,
Ollama, Groq and OpenRouter requests, retries, credits and the tokens-per-minute limit, secrets
and the import boundary. No network: every backend call goes to a scripted transport or the
fake client."""

import gzip
import hashlib
import json
import pickle
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from sentinel.llm import (
    CacheMiss,
    CreditsExhausted,
    FakeLlmClient,
    FakeReply,
    GroqClient,
    LlmCache,
    LlmError,
    Message,
    OllamaClient,
    OpenRouterClient,
    QuotaExhausted,
    RequestTooLarge,
    Secret,
    TokenRateLimiter,
    backend_schema,
    load_prompt,
    load_secret,
)
from sentinel.llm.cache import write_bundle
from sentinel.llm.http import HttpReply, TransportError
from sentinel.llm.openai_compat import parse_wait
from sentinel.llm.openrouter import reset_wait
from sentinel.llm.secrets import redact

REPO_ROOT = Path(__file__).resolve().parents[1]
MESSAGES = [
    Message(role="system", content="Answer with JSON."),
    Message(role="user", content="a is 1 and b is x"),
]
KEY = Secret("gsk_test0123456789abcdefTESTKEY")
OPENROUTER_KEY = Secret("sk-or-v1-0123456789abcdef0123456789abcdefTEST")  # pragma: allowlist secret
ROUTING = {"order": ["groq"], "allow_fallbacks": False, "require_parameters": True}
REASONING = {"effort": "low", "exclude": True}
DIGEST = "sha256:" + "ab" * 32


class Pair(BaseModel):
    a: int
    b: str


class Other(BaseModel):
    a: int


class Item(BaseModel):
    name: str
    crew: dict[str, int]


class Basket(BaseModel):
    """A docstring that does not reach the backend."""

    items: tuple[Item, ...]


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class ScriptedTransport:
    """Answers HTTP requests from a list; records method, URL, JSON body and headers."""

    def __init__(self, replies: list[HttpReply | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str, object, dict[str, str]]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> HttpReply:
        self.calls.append((method, url, None if body is None else json.loads(body), dict(headers)))
        if not self.replies:
            raise AssertionError(f"unexpected request {method} {url}")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def chat_ok(text: str, prompt: int = 10, completion: int = 5, limit: str = "8000") -> HttpReply:
    body = {
        "model": "openai/gpt-oss-120b",
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }
    return HttpReply(200, json.dumps(body).encode(), {"x-ratelimit-limit-tokens": limit})


def groq(transport: ScriptedTransport, **settings: object) -> tuple[GroqClient, FakeClock]:
    clock = FakeClock()
    client = GroqClient(
        "openai/gpt-oss-120b",
        api_key=KEY,
        env_file=None,
        transport=transport,
        clock=clock.now,
        sleep=clock.sleep,
        **settings,  # type: ignore[arg-type]
    )
    return client, clock


def routed_ok(text: str, provider: str | None = "Groq", **extra: object) -> HttpReply:
    """An OpenRouter answer (no rate-limit headers), naming its provider if given."""
    body: dict[str, object] = {
        "id": "gen-1",
        "model": "openai/gpt-oss-120b",
        "choices": [
            {"message": {"content": text}, "finish_reason": "stop", "native_finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.00012},
        **extra,
    }
    if provider is not None:
        body["provider"] = provider
    return HttpReply(200, json.dumps(body).encode(), {})


def routed_error(status: int, error: Mapping[str, object], **headers: str) -> HttpReply:
    body = json.dumps({"error": dict(error)}).encode()
    return HttpReply(status, body, {name.replace("_", "-"): v for name, v in headers.items()})


def openrouter(
    transport: ScriptedTransport, **settings: object
) -> tuple[OpenRouterClient, FakeClock]:
    clock = FakeClock()
    options: dict[str, object] = {
        "tokens_per_minute": None,
        "extra": {"provider": ROUTING, "reasoning": REASONING},
        **settings,
    }
    client = OpenRouterClient(
        "openai/gpt-oss-120b",
        api_key=OPENROUTER_KEY,
        env_file=None,
        transport=transport,
        clock=clock.now,
        sleep=clock.sleep,
        **options,  # type: ignore[arg-type]
    )
    return client, clock


def test_record_then_replay_returns_the_recorded_reply(tmp_path: Path) -> None:
    path = tmp_path / "fake.jsonl"
    recorder = FakeLlmClient(
        ['{"a": 1, "b": "x"}'], cache=LlmCache(path), mode="record", latency_s=1.5
    )
    first = recorder.complete(MESSAGES, schema=Pair, seed=7, max_tokens=64)
    assert first.value == Pair(a=1, b="x") and not first.cache_hit

    cache = LlmCache(path)
    replayer = FakeLlmClient([], cache=cache, mode="replay")
    again = replayer.complete(MESSAGES, schema=Pair, seed=7, max_tokens=64)
    assert again.cache_hit and (again.text, again.latency_s, again.key) == (
        first.text,
        1.5,
        first.key,
    )
    assert replayer.requests == [] and replayer.stats.hit_rate == 1.0
    with pytest.raises(CacheMiss):
        replayer.complete(MESSAGES, schema=Pair, seed=8, max_tokens=64)

    bundle = tmp_path / "llm_cache.jsonl.gz"
    write_bundle(bundle, cache.used.values())
    from_bundle = FakeLlmClient([], cache=LlmCache(bundle), mode="replay")
    assert from_bundle.complete(MESSAGES, schema=Pair, seed=7, max_tokens=64).text == first.text
    write_bundle(tmp_path / "again.jsonl.gz", cache.used.values())
    assert (tmp_path / "again.jsonl.gz").read_bytes() == bundle.read_bytes()
    with pytest.raises(PermissionError):
        LlmCache(bundle).put(recorder.requests[0], recorder.cache.entries()[0].reply)  # type: ignore[union-attr]


def test_auto_mode_calls_the_backend_on_a_miss_only(tmp_path: Path) -> None:
    client = FakeLlmClient(
        ['{"a": 1, "b": "x"}', '{"a": 2, "b": "y"}'], cache=LlmCache(tmp_path / "c.jsonl")
    )
    assert client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=64).value == Pair(a=1, b="x")
    assert client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=64).cache_hit
    assert client.complete(MESSAGES, schema=Pair, seed=2, max_tokens=64).value == Pair(a=2, b="y")
    assert (client.stats.calls, client.stats.cache_hits, client.stats.backend_calls) == (3, 1, 2)
    with pytest.raises(ValueError, match="replay mode needs a cache"):
        FakeLlmClient([], mode="replay")


def test_the_key_covers_backend_model_digest_messages_schema_and_parameters() -> None:
    def key(client: FakeLlmClient | OllamaClient, **change: object) -> str:
        settings: dict[str, object] = {
            "schema": Pair,
            "temperature": 0.0,
            "seed": 1,
            "max_tokens": 64,
        }
        settings.update(change)
        messages = settings.pop("messages", MESSAGES)
        return client.request(messages, **settings).key  # type: ignore[arg-type]

    fake = FakeLlmClient([])
    base = key(fake)
    assert key(fake) == base
    others = [
        key(FakeLlmClient([], model="other")),
        key(fake, messages=[*MESSAGES[:1], Message(role="user", content="a is 2")]),
        key(fake, schema=Other),
        key(fake, temperature=0.5),
        key(fake, seed=2),
        key(fake, max_tokens=65),
    ]
    ollama = [
        OllamaClient("m", num_ctx=n, digest=d, host="http://ollama", env_file=None)
        for n, d in ((4096, DIGEST), (4096, "sha256:" + "cd" * 32), (8192, DIGEST))
    ]
    others += [key(client) for client in ollama]
    assert len({base, *others}) == len(others) + 1


def test_a_cut_off_last_line_is_skipped_and_a_corrupt_line_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    client = FakeLlmClient(['{"a": 1, "b": "x"}'], cache=LlmCache(path))
    client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=64)
    good = path.read_text(encoding="utf-8")
    path.write_text(good + good[: len(good) // 2], encoding="utf-8")
    cache = LlmCache(path)
    assert len(cache) == 1 and cache.skipped_lines == 1
    path.write_text(good[: len(good) // 2] + "\n" + good, encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt cache entry"):
        LlmCache(path)


def test_schema_violations_come_back_as_structured_errors() -> None:
    client = FakeLlmClient(
        ['{"a": "one"}', "not json", FakeReply('{"a": 1, "b"', finish_reason="length"), "  "]
    )
    violation = client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=64)
    assert violation.value is None and violation.parsed == {"a": "one"}
    assert violation.error is not None and violation.error.kind == "schema"
    assert {(d.loc, d.type) for d in violation.error.details} == {
        ("a", "int_parsing"),
        ("b", "missing"),
    }
    kinds = [client.complete(MESSAGES, schema=Pair, seed=s, max_tokens=64).error for s in (2, 3, 4)]
    assert [e.kind if e else None for e in kinds] == ["json", "truncated", "empty"]


def test_backend_schema_inlines_references_and_drops_titles() -> None:
    schema = backend_schema(Basket)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text and '"title"' not in text
    assert '"description"' not in text
    item = schema["properties"]["items"]["items"]  # type: ignore[index, call-overload]
    assert item["properties"]["crew"]["additionalProperties"] == {"type": "integer"}  # type: ignore[index, call-overload]
    assert item["required"] == ["name", "crew"]  # type: ignore[index, call-overload]


def test_ollama_sends_schema_seed_and_context_after_checking_the_digest() -> None:
    show = HttpReply(200, json.dumps({"modelfile": f"FROM /m/blobs/sha256-{'ab' * 32}\n"}).encode())
    chat = HttpReply(
        200,
        json.dumps(
            {
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": '{"a": 1, "b": "x"}'},
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 6,
                "eval_duration": 1_500_000_000,
            }
        ).encode(),
    )
    transport = ScriptedTransport([show, chat])
    client = OllamaClient(
        "qwen2.5:7b",
        num_ctx=4096,
        digest=DIGEST,
        host="http://ollama:1",
        transport=transport,
        env_file=None,
    )
    response = client.complete(MESSAGES, schema=Pair, seed=5, max_tokens=99)
    assert response.value == Pair(a=1, b="x") and (
        response.prompt_tokens,
        response.completion_tokens,
    ) == (12, 6)
    (_, show_url, _, _), (_, chat_url, body, _) = transport.calls
    assert show_url == "http://ollama:1/api/show" and chat_url == "http://ollama:1/api/chat"
    assert isinstance(body, dict) and body["format"] == backend_schema(Pair) and not body["stream"]
    assert body["options"] == {"temperature": 0.0, "seed": 5, "num_predict": 99, "num_ctx": 4096}

    pinned = OllamaClient(
        "qwen2.5:7b",
        num_ctx=4096,
        digest="sha256:" + "cd" * 32,
        transport=ScriptedTransport([show]),
        env_file=None,
    )
    with pytest.raises(LlmError, match="pins"):
        pinned.complete(MESSAGES, schema=Pair, seed=5, max_tokens=99)
    full = ScriptedTransport(
        [
            show,
            HttpReply(
                200, json.dumps({"message": {"content": "{}"}, "prompt_eval_count": 4096}).encode()
            ),
        ]
    )
    with pytest.raises(RequestTooLarge):
        OllamaClient(
            "qwen2.5:7b", num_ctx=4096, digest=DIGEST, transport=full, env_file=None
        ).complete(MESSAGES, schema=Pair, seed=5, max_tokens=99)


def test_groq_backs_off_on_a_scripted_429_honouring_retry_after() -> None:
    transport = ScriptedTransport(
        [
            HttpReply(429, b'{"error": {"message": "rate limit"}}', {"retry-after": "7"}),
            HttpReply(503, b"busy"),
            TransportError("POST https://api.groq.com failed: timed out"),
            chat_ok('{"a": 1, "b": "x"}'),
        ]
    )
    client, clock = groq(transport, tokens_per_minute=None, backoff_s=2.0)
    response = client.complete(MESSAGES, schema=Pair, seed=3, max_tokens=50)
    assert response.value == Pair(a=1, b="x")
    assert clock.sleeps == [7.0, 4.0, 8.0] and client.retries == 3 and len(transport.calls) == 4
    _, url, body, headers = transport.calls[0]
    assert url.endswith("/openai/v1/chat/completions") and isinstance(body, dict)
    assert (body["seed"], body["max_completion_tokens"], body["temperature"]) == (3, 50, 0.0)
    assert body["response_format"]["json_schema"]["schema"] == backend_schema(Pair)
    assert headers["Authorization"] == f"Bearer {KEY.reveal()}"
    assert (
        parse_wait("2m59.5s") == 179.5 and parse_wait("350ms") == 0.35 and parse_wait("x") is None
    )


def test_groq_stops_on_a_long_rate_limit_wait_and_on_a_too_large_request() -> None:
    client, clock = groq(
        ScriptedTransport([HttpReply(429, b"{}", {"retry-after": "3600"})]), tokens_per_minute=None
    )
    with pytest.raises(QuotaExhausted) as info:
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert info.value.retry_after_s == 3600 and clock.sleeps == []
    client, _ = groq(
        ScriptedTransport([HttpReply(413, b'{"error": {"message": "too large"}}')]),
        tokens_per_minute=None,
    )
    with pytest.raises(RequestTooLarge):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    client, _ = groq(
        ScriptedTransport([HttpReply(500, b"down")] * 3), tokens_per_minute=None, max_retries=2
    )
    with pytest.raises(LlmError, match="gave up after 3 attempts"):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    limited = [HttpReply(429, b"{}", {"retry-after": "30"})] * 3
    client, clock = groq(ScriptedTransport(limited), tokens_per_minute=None, max_retries=2)
    with pytest.raises(QuotaExhausted, match="still rate limited after 3 attempts"):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert clock.sleeps == [30.0, 30.0]


def test_groq_returns_a_failed_generation_as_an_answer() -> None:
    error = {"error": {"code": "json_validate_failed", "failed_generation": '{"a": "x"}'}}
    client, _ = groq(
        ScriptedTransport([HttpReply(400, json.dumps(error).encode())]), tokens_per_minute=None
    )
    response = client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert response.finish_reason == "json_validate_failed" and response.parsed == {"a": "x"}
    assert response.error is not None and response.error.kind == "schema"
    unparsed = {"error": {"code": "output_parse_failed", "failed_generation": "No events."}}
    client, _ = groq(
        ScriptedTransport([HttpReply(400, json.dumps(unparsed).encode())]), tokens_per_minute=None
    )
    response = client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert response.finish_reason == "output_parse_failed" and response.text == "No events."
    assert response.error is not None and response.error.kind == "json"
    other = {"error": {"code": "invalid_api_key"}}
    client, _ = groq(
        ScriptedTransport([HttpReply(400, json.dumps(other).encode())]), tokens_per_minute=None
    )
    with pytest.raises(LlmError):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)


def test_the_token_limiter_spaces_requests_within_a_minute() -> None:
    clock = FakeClock()
    limiter = TokenRateLimiter(100, clock=clock.now, sleep=clock.sleep)
    first = limiter.acquire(60)
    clock.t = 10.0
    second = limiter.acquire(60)
    assert clock.sleeps == [50.0] and clock.t == 60.0
    limiter.settle(second, 20)
    assert limiter.used() == 20
    limiter.acquire(500)  # capped at the whole limit: waits until the window is empty
    assert clock.t == 120.0 and limiter.used() == 100
    assert first[1] == 60.0

    transport = ScriptedTransport(
        [
            chat_ok('{"a": 1, "b": "x"}', 700, 300, limit="1000"),
            chat_ok('{"a": 1, "b": "y"}', 700, 300, limit="1000"),
        ]
    )
    client, clock = groq(transport, tokens_per_minute=1000)
    client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=2000)
    client.complete(MESSAGES, schema=Pair, seed=2, max_tokens=2000)
    assert clock.sleeps == [60.0]  # the first used 1000 tokens, so the second waits a minute


def test_the_limiter_follows_the_reported_limit_and_falls_back_to_the_config() -> None:
    def two_calls(client: GroqClient | OpenRouterClient) -> None:
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=2000)
        client.complete(MESSAGES, schema=Pair, seed=2, max_tokens=2000)

    answers = [chat_ok('{"a": 1, "b": "x"}', 700, 300), chat_ok('{"a": 1, "b": "y"}', 700, 300)]
    raised, clock = groq(ScriptedTransport(answers), tokens_per_minute=1000)
    two_calls(raised)  # Groq reports 8,000 tokens per minute: the second call fits
    assert clock.sleeps == [] and raised.limiter is not None and raised.limiter.limit == 8000
    reported = [chat_ok('{"a": 1, "b": "x"}', 700, 300, limit="1000")] * 2
    learned, clock = groq(ScriptedTransport(reported), tokens_per_minute=None)
    two_calls(learned)  # no configured limit: the reported one applies from the first answer
    assert clock.sleeps == [60.0]
    silent = [routed_ok('{"a": 1, "b": "x"}'), routed_ok('{"a": 1, "b": "y"}')]
    configured, clock = openrouter(ScriptedTransport(silent), tokens_per_minute=1000)
    two_calls(configured)  # OpenRouter reports no limit: the configured one applies
    assert configured.limiter is not None and configured.limiter.limit == 1000
    assert clock.sleeps == [60.0]


def test_the_groq_request_and_its_cache_key_are_unchanged_by_the_shared_client() -> None:
    """The key and body of a fixed request as computed before WP6c, so that the recorded Groq
    caches still answer."""
    transport = ScriptedTransport([chat_ok('{"a": 1, "b": "x"}')])
    client, _ = groq(
        transport,
        tokens_per_minute=None,
        extra={"reasoning_effort": "low", "include_reasoning": False},
    )
    request = client.request(MESSAGES, schema=Pair, temperature=0.0, seed=3, max_tokens=50)
    assert request.key == (
        "87c7c13ca608fdde880615027dbb920d"  # pragma: allowlist secret
        "fd01900b409d174185419d7a92c47c5d"  # pragma: allowlist secret
    )
    client.complete(MESSAGES, schema=Pair, seed=3, max_tokens=50)
    body = json.dumps(transport.calls[0][2]).encode("utf-8")
    assert hashlib.sha256(body).hexdigest() == (
        "2e648c0095547bb1a0efbe251faf27c9"  # pragma: allowlist secret
        "48978e128e6ebe46a66ee24746a0fe45"  # pragma: allowlist secret
    )


def test_openrouter_sends_the_pinned_routing_and_records_the_provider(tmp_path: Path) -> None:
    cache = LlmCache(tmp_path / "openrouter.jsonl")
    metadata = {"endpoints": {"available": [{"provider": "Groq", "selected": True}]}}
    transport = ScriptedTransport(
        [
            routed_ok('{"a": 1, "b": "x"}'),
            routed_ok('{"a": 2, "b": "y"}', provider=None, openrouter_metadata=metadata),
        ]
    )
    client, _ = openrouter(transport, cache=cache)
    response = client.complete(MESSAGES, schema=Pair, seed=3, max_tokens=50)
    assert response.value == Pair(a=1, b="x")
    _, url, body, headers = transport.calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions" and isinstance(body, dict)
    assert body["provider"] == ROUTING and body["reasoning"] == REASONING
    assert (body["seed"], body["max_tokens"], body["temperature"]) == (3, 50, 0.0)
    assert "max_completion_tokens" not in body
    assert body["response_format"]["json_schema"]["schema"] == backend_schema(Pair)
    assert headers["Authorization"] == f"Bearer {OPENROUTER_KEY.reveal()}"
    assert headers["X-OpenRouter-Metadata"] == "enabled"
    client.complete(MESSAGES, schema=Pair, seed=4, max_tokens=50)
    first, second = cache.entries()
    assert first.backend == "openrouter" and first.request["options"] == {
        "response_format": "json_schema",
        "provider": ROUTING,
        "reasoning": REASONING,
    }
    assert first.reply.meta["provider"] == "Groq" and first.reply.meta["cost"] == 0.00012
    assert first.reply.meta["generation_id"] == "gen-1"
    assert second.reply.meta["provider"] == "Groq"  # from the router metadata
    cerebras, _ = openrouter(
        ScriptedTransport([]),
        extra={"provider": {**ROUTING, "order": ["cerebras"]}, "reasoning": REASONING},
    )
    settings: dict[str, object] = {"schema": Pair, "temperature": 0.0, "seed": 3, "max_tokens": 50}
    assert cerebras.request(MESSAGES, **settings).key != client.request(MESSAGES, **settings).key  # type: ignore[arg-type]


def test_openrouter_rejects_an_answer_of_a_provider_outside_the_pin(tmp_path: Path) -> None:
    cache = LlmCache(tmp_path / "openrouter.jsonl")
    client, _ = openrouter(
        ScriptedTransport([routed_ok('{"a": 1, "b": "x"}', provider="Cerebras")]), cache=cache
    )
    with pytest.raises(LlmError, match="not by the pinned"):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert len(cache) == 0 and not (tmp_path / "openrouter.jsonl").exists()


def test_openrouter_stops_for_credits_and_waits_for_the_in_flight_budget() -> None:
    no_credits = routed_error(
        402,
        {"code": 402, "message": "Insufficient credits", "metadata": {"limit_source": "x"}},
    )
    client, clock = openrouter(ScriptedTransport([no_credits]))
    with pytest.raises(CreditsExhausted) as info:
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert isinstance(info.value, QuotaExhausted) and clock.sleeps == []
    assert "add credits at https://openrouter.ai/settings/credits" in str(info.value)
    assert info.value.resume_hint.startswith("add credits")
    in_flight = routed_error(
        402,
        {"code": 402, "metadata": {"limit_source": "openrouter_in_flight_budget"}},
        retry_after="3",
    )
    client, clock = openrouter(ScriptedTransport([in_flight, routed_ok('{"a": 1, "b": "x"}')]))
    assert client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50).value == Pair(a=1, b="x")
    assert clock.sleeps == [3.0] and client.retries == 1


def test_openrouter_backs_off_on_429_and_on_an_error_inside_a_200() -> None:
    reset = str(int((time.time() + 20) * 1000))  # epoch milliseconds
    transport = ScriptedTransport(
        [
            routed_error(429, {"code": 429, "message": "Rate limit exceeded"}, retry_after="7"),
            routed_error(200, {"code": 502, "message": "upstream error"}),
            routed_error(429, {"code": 429}, x_ratelimit_reset=reset),
            routed_ok('{"a": 1, "b": "x"}'),
        ]
    )
    client, clock = openrouter(transport, backoff_s=2.0)
    assert client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50).value == Pair(a=1, b="x")
    assert clock.sleeps[:2] == [7.0, 4.0] and clock.sleeps[2] == pytest.approx(20, abs=2)
    assert reset_wait("1800000000000", now=1_799_999_990.0) == pytest.approx(10.0)
    assert reset_wait("12") == 12.0 and reset_wait(None) is None
    client, clock = openrouter(
        ScriptedTransport([routed_error(429, {"code": 429}, retry_after="3600")])
    )
    with pytest.raises(QuotaExhausted) as info:
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert info.value.retry_after_s == 3600 and clock.sleeps == []
    client, _ = openrouter(ScriptedTransport([routed_error(401, {"code": 401})]))
    with pytest.raises(LlmError, match="HTTP 401"):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)


def test_openrouter_returns_a_failed_generation_of_the_provider_as_an_answer(
    tmp_path: Path,
) -> None:
    raw = {"error": {"code": "json_validate_failed", "failed_generation": '{"a": "x"}'}}
    metadata = {"provider_name": "Groq", "raw": json.dumps(raw)}
    failed = routed_error(
        400, {"code": 400, "message": "Provider returned error", "metadata": metadata}
    )
    cache = LlmCache(tmp_path / "openrouter.jsonl")
    client, _ = openrouter(ScriptedTransport([failed]), cache=cache)
    response = client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert response.finish_reason == "json_validate_failed" and response.parsed == {"a": "x"}
    assert response.error is not None and response.error.kind == "schema"
    assert cache.entries()[0].reply.meta["provider"] == "Groq"
    client, _ = openrouter(ScriptedTransport([routed_error(400, {"code": 400})]))
    with pytest.raises(LlmError):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)


def test_a_cache_without_prompts_replays_by_key_and_holds_no_message_text(
    tmp_path: Path,
) -> None:
    private = [
        Message(role="system", content="Report the absences as JSON."),
        Message(role="user", content="Zofia Wrona is in hospital with pneumonia until Friday."),
    ]
    path = tmp_path / "private.jsonl"
    recorder = FakeLlmClient(
        ['{"a": 1, "b": "x"}'], cache=LlmCache(path, store_prompts=False), mode="record"
    )
    first = recorder.complete(private, schema=Pair, seed=7, max_tokens=64)
    stored = path.read_text(encoding="utf-8")
    for text in [m.content for m in private] + ["Zofia", "hospital", "pneumonia"]:
        assert text not in stored
    (entry,) = LlmCache(path, store_prompts=False).entries()
    assert entry.key == first.key and "messages" not in entry.request
    assert entry.request["store_prompts"] is False and entry.request["schema_name"] == "Pair"

    replayer = FakeLlmClient([], cache=LlmCache(path, store_prompts=False), mode="replay")
    again = replayer.complete(private, schema=Pair, seed=7, max_tokens=64)
    assert again.cache_hit and again.value == Pair(a=1, b="x") and again.key == first.key
    with pytest.raises(CacheMiss):
        replayer.complete(
            [private[0], Message(role="user", content="other")], schema=Pair, seed=7, max_tokens=64
        )
    assert replayer.cache is not None
    bundle = tmp_path / "llm_cache.jsonl.gz"
    write_bundle(bundle, replayer.cache.used.values())
    assert "Zofia" not in gzip.decompress(bundle.read_bytes()).decode("utf-8")
    from_bundle = FakeLlmClient([], cache=LlmCache(bundle, store_prompts=False), mode="replay")
    assert from_bundle.complete(private, schema=Pair, seed=7, max_tokens=64).text == first.text

    full = tmp_path / "full.jsonl"
    FakeLlmClient(['{"a": 1, "b": "x"}'], cache=LlmCache(full)).complete(
        private, schema=Pair, seed=7, max_tokens=64
    )
    assert "Zofia" in full.read_text(encoding="utf-8")  # research runs keep the full record
    with pytest.raises(ValueError, match="holds message text"):
        LlmCache(full, store_prompts=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: int
    b: Literal["x", "y"]


def test_a_cache_without_prompts_stores_an_invalid_answer_only_as_its_issue_list(
    tmp_path: Path,
) -> None:
    answers = [
        '{"a": "one", "b": "x", "illness": "pneumonia"}',
        "Zofia is in hospital with pneumonia.",
        '{"a": 1, "b": "flu"}',
        '{"a": 2, "b": "y"}',
    ]
    path = tmp_path / "private.jsonl"
    recorder = FakeLlmClient(answers, cache=LlmCache(path, store_prompts=False), mode="record")
    recorded = [
        recorder.complete(MESSAGES, schema=Strict, seed=seed, max_tokens=64) for seed in range(4)
    ]
    stored = path.read_text(encoding="utf-8")
    for word in ("pneumonia", "Zofia", "hospital", "illness", "flu", "one"):
        assert word not in stored
    assert [r.error.kind if r.error else None for r in recorded] == [
        "schema",
        "json",
        "schema",
        None,
    ]
    assert recorded[0].error is not None and recorded[2].error is not None
    assert {(d.loc, d.type) for d in recorded[0].error.details} == {
        ("a", "int_parsing"),
        ("*", "extra_forbidden"),
    }
    assert [(d.loc, d.type) for d in recorded[2].error.details] == [("b", "literal_error")]
    assert [(r.text, r.parsed) for r in recorded[:3]] == [("", None)] * 3
    assert recorded[3].value == Strict(a=2, b="y") and recorded[3].text == answers[3]

    replayer = FakeLlmClient([], cache=LlmCache(path, store_prompts=False), mode="replay")
    replayed = [
        replayer.complete(MESSAGES, schema=Strict, seed=seed, max_tokens=64) for seed in range(4)
    ]
    assert all(r.cache_hit for r in replayed)
    assert [(r.text, r.parsed, r.value, r.error) for r in replayed] == [
        (r.text, r.parsed, r.value, r.error) for r in recorded
    ]

    full = FakeLlmClient(answers[:1], cache=LlmCache(tmp_path / "full.jsonl"))
    kept = full.complete(MESSAGES, schema=Strict, seed=0, max_tokens=64)
    assert kept.text == answers[0] and kept.parsed is not None  # research runs keep the text
    assert "pneumonia" in (tmp_path / "full.jsonl").read_text(encoding="utf-8")


def test_the_key_never_shows_in_reprs_errors_or_cache_files(tmp_path: Path) -> None:
    secret = Secret("gsk_live_ABCDEFGHIJKLMNOPQRSTUVWX")
    value = secret.reveal()
    assert value not in repr(secret) + str(secret) + f"{secret}"
    with pytest.raises(TypeError):
        pickle.dumps(secret)
    echo = {"error": {"message": f"Invalid API Key: {value} (key gsk_otherABCDEFGH12345)"}}
    cache = LlmCache(tmp_path / "groq.jsonl")
    transport = ScriptedTransport(
        [HttpReply(401, json.dumps(echo).encode()), chat_ok('{"a": 1, "b": "x"}')]
    )
    client = GroqClient(
        "openai/gpt-oss-120b",
        tokens_per_minute=None,
        api_key=secret,
        env_file=None,
        cache=cache,
        transport=transport,
    )
    assert value not in repr(client) and "redacted" in repr(client)
    with pytest.raises(LlmError) as info:
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert value not in str(info.value) and "gsk_other" not in str(info.value)
    assert "[REDACTED]" in str(info.value)
    client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert value not in (tmp_path / "groq.jsonl").read_text(encoding="utf-8")


def test_the_openrouter_key_never_shows_in_reprs_errors_or_cache_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = OPENROUTER_KEY.reveal()
    other = "sk-or-v1-ffffffffffffffffffffffffffffffff"  # pragma: allowlist secret
    echo = {"code": 401, "message": f"No auth credentials found for {value} or {other}"}
    cache = LlmCache(tmp_path / "openrouter.jsonl")
    client, _ = openrouter(
        ScriptedTransport([routed_error(401, echo), routed_ok('{"a": 1, "b": "x"}')]),
        cache=cache,
    )
    assert value not in repr(client) and "redacted" in repr(client)
    with pytest.raises(LlmError) as info:
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert value not in str(info.value) and other not in str(info.value)
    assert str(info.value).count("[REDACTED]") == 2 and redact(other) == "[REDACTED]"
    client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert value not in (tmp_path / "openrouter.jsonl").read_text(encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    keyless = OpenRouterClient(
        "m",
        tokens_per_minute=None,
        env_file=tmp_path / "absent.env",
        transport=ScriptedTransport([]),
    )
    with pytest.raises(LlmError, match="OPENROUTER_API_KEY is not set"):
        keyless.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)


def test_the_key_comes_from_the_environment_or_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    fake_key = "gsk_fromfile1234567"  # pragma: allowlist secret
    env.write_text(f'# keys\nOTHER=1\nexport GROQ_API_KEY="{fake_key}"\n', encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    found = load_secret("GROQ_API_KEY", env_file=env)
    assert found is not None and found.reveal() == "gsk_fromfile1234567"
    assert load_secret("ABSENT", env_file=env) is None
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fromenv12345678")
    found = load_secret("GROQ_API_KEY", env_file=env)
    assert found is not None and found.reveal() == "gsk_fromenv12345678"
    monkeypatch.delenv("GROQ_API_KEY")
    client = GroqClient(
        "m",
        tokens_per_minute=None,
        env_file=tmp_path / "absent.env",
        transport=ScriptedTransport([]),
    )
    with pytest.raises(LlmError, match="GROQ_API_KEY is not set"):
        client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)


def test_replaying_needs_neither_a_key_nor_a_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "groq.jsonl"
    recorder, _ = groq(
        ScriptedTransport([chat_ok('{"a": 1, "b": "x"}')]),
        tokens_per_minute=None,
        cache=LlmCache(path),
    )
    recorder.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    replayer = GroqClient(
        "openai/gpt-oss-120b",
        tokens_per_minute=None,
        env_file=None,
        cache=LlmCache(path),
        mode="replay",
        transport=ScriptedTransport([]),
    )
    assert replayer.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50).value == Pair(a=1, b="x")
    ollama = OllamaClient(
        "m",
        num_ctx=4096,
        digest=DIGEST,
        env_file=None,
        transport=ScriptedTransport([]),
        mode="replay",
        cache=LlmCache(tmp_path / "o.jsonl"),
    )
    with pytest.raises(CacheMiss):
        ollama.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)


def test_prompts_are_versioned_files() -> None:
    extract = load_prompt("wbs_extract", "v1")
    assert extract.text.startswith("You extract") and len(extract.sha256) == 64
    assert "$issues" in load_prompt("wbs_repair", "v1").text
    assert load_prompt("wbs_repair", "v1").render(issues="- one").count("- one") == 1
    with pytest.raises(FileNotFoundError):
        load_prompt("wbs_extract", "v0")


def test_only_the_wbs_and_experiment_packages_import_the_llm_layer() -> None:
    """No simulation, scheduling, forecasting, policy or agent module imports `sentinel.llm`,
    `sentinel.wbs` or `sentinel.interpret`, so no rollout or simulation path can call an LLM;
    the interpretation layer and the experiments may (spec section 10)."""
    imports = re.compile(r"^\s*(?:from|import)\s+sentinel\.(llm|wbs|interpret)\b", re.MULTILINE)
    source = REPO_ROOT / "src" / "sentinel"
    offenders = []
    for path in sorted(source.rglob("*.py")):
        package = path.relative_to(source).parts[0]
        llm_side = ("llm", "wbs", "interpret")
        allowed = {"llm": llm_side, "wbs": llm_side, "interpret": llm_side, "experiments": llm_side}
        found = set(imports.findall(path.read_text(encoding="utf-8")))
        if found - set(allowed.get(package, ())):
            offenders.append(str(path.relative_to(source)))
    assert offenders == []
