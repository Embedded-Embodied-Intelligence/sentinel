"""LLM layer (WP6a): record/replay cache, schema violations, Ollama and Groq requests, Groq
retries and the tokens-per-minute limit, secrets and the import boundary. No network: every
backend call goes to a scripted transport or the fake client."""

import json
import pickle
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import BaseModel

from sentinel.llm import (
    CacheMiss,
    FakeLlmClient,
    FakeReply,
    GroqClient,
    LlmCache,
    LlmError,
    Message,
    OllamaClient,
    QuotaExhausted,
    RequestTooLarge,
    Secret,
    TokenRateLimiter,
    backend_schema,
    load_prompt,
    load_secret,
)
from sentinel.llm.cache import write_bundle
from sentinel.llm.groq import parse_wait
from sentinel.llm.http import HttpReply, TransportError

REPO_ROOT = Path(__file__).resolve().parents[1]
MESSAGES = [
    Message(role="system", content="Answer with JSON."),
    Message(role="user", content="a is 1 and b is x"),
]
KEY = Secret("gsk_test0123456789abcdefTESTKEY")
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


def chat_ok(text: str, prompt: int = 10, completion: int = 5) -> HttpReply:
    body = {
        "model": "openai/gpt-oss-120b",
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }
    return HttpReply(200, json.dumps(body).encode(), {"x-ratelimit-limit-tokens": "8000"})


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


def test_groq_returns_a_failed_generation_as_an_answer() -> None:
    error = {"error": {"code": "json_validate_failed", "failed_generation": '{"a": "x"}'}}
    client, _ = groq(
        ScriptedTransport([HttpReply(400, json.dumps(error).encode())]), tokens_per_minute=None
    )
    response = client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=50)
    assert response.finish_reason == "json_validate_failed" and response.parsed == {"a": "x"}
    assert response.error is not None and response.error.kind == "schema"


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
        [chat_ok('{"a": 1, "b": "x"}', 700, 300), chat_ok('{"a": 1, "b": "y"}', 700, 300)]
    )
    client, clock = groq(transport, tokens_per_minute=1000)
    client.complete(MESSAGES, schema=Pair, seed=1, max_tokens=2000)
    client.complete(MESSAGES, schema=Pair, seed=2, max_tokens=2000)
    assert clock.sleeps == [60.0]  # the first used 1000 tokens, so the second waits a minute


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
    """No simulation, scheduling, forecasting, policy or agent module imports `sentinel.llm` or
    `sentinel.wbs`, so no rollout or simulation path can call an LLM."""
    imports = re.compile(r"^\s*(?:from|import)\s+sentinel\.(llm|wbs)\b", re.MULTILINE)
    source = REPO_ROOT / "src" / "sentinel"
    offenders = []
    for path in sorted(source.rglob("*.py")):
        package = path.relative_to(source).parts[0]
        allowed = {"llm": ("llm", "wbs"), "wbs": ("llm", "wbs"), "experiments": ("llm", "wbs")}
        found = set(imports.findall(path.read_text(encoding="utf-8")))
        if found - set(allowed.get(package, ())):
            offenders.append(str(path.relative_to(source)))
    assert offenders == []
