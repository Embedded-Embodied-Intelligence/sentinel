"""Local Ollama backend: `/api/chat` with the JSON schema as `format` (constrained decoding),
`options.seed`, `temperature`, `num_predict` and a fixed `num_ctx`; the digest of the model's
weights, read from `/api/show`, is part of every cache key (Ollama 0.40)."""

import json
import re
import time
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from sentinel.llm.cache import CacheMode, LlmCache
from sentinel.llm.client import BaseClient
from sentinel.llm.core import LlmError, Reply, Request, RequestTooLarge
from sentinel.llm.http import Transport, urllib_transport
from sentinel.llm.secrets import DEFAULT_ENV_FILE, load_setting

DEFAULT_HOST = "http://127.0.0.1:11434"
HOST_VARIABLE = "OLLAMA_HOST"
_WEIGHTS = re.compile(r"^FROM\s+\S*sha256-([0-9a-f]{64})\s*$", re.MULTILINE)


class OllamaClient(BaseClient):
    """An Ollama model on the local server; `digest` pins the weights (checked against the
    server before the first backend call, so replaying from the cache needs no server)."""

    backend = "ollama"

    def __init__(
        self,
        model: str,
        *,
        num_ctx: int,
        digest: str | None = None,
        host: str | None = None,
        keep_alive: str = "30m",
        timeout_s: float = 1800.0,
        cache: LlmCache | None = None,
        mode: CacheMode = "auto",
        transport: Transport = urllib_transport,
        env_file: Path | None = DEFAULT_ENV_FILE,
    ) -> None:
        super().__init__(model, cache=cache, mode=mode)
        if num_ctx < 1:
            raise ValueError(f"num_ctx must be positive, got {num_ctx}")
        self.num_ctx = num_ctx
        self.host = (host or load_setting(HOST_VARIABLE, env_file=env_file) or DEFAULT_HOST).rstrip(
            "/"
        )
        self.keep_alive = keep_alive
        self.timeout_s = timeout_s
        self.transport = transport
        self._pinned = digest
        self._server_digest: str | None = None
        self._checked = False

    @property
    def digest(self) -> str:
        return self._pinned if self._pinned is not None else self.server_digest()

    def options(self) -> dict[str, JsonValue]:
        return {"num_ctx": self.num_ctx}

    def server_digest(self) -> str:
        """`sha256:<hex>` of the weights blob named by the `FROM` line of `/api/show`."""
        if self._server_digest is None:
            shown = self._call("POST", "/api/show", {"model": self.model}, timeout=60.0)
            match = _WEIGHTS.search(str(shown.get("modelfile", "")))
            if match is None:
                raise LlmError(f"Ollama /api/show reports no weights digest for {self.model}")
            self._server_digest = f"sha256:{match.group(1)}"
        return self._server_digest

    def server_version(self) -> str | None:
        """The server's version from `/api/version`."""
        version = self._call("GET", "/api/version", None, timeout=10.0).get("version")
        return None if version is None else str(version)

    def _send(self, request: Request) -> Reply:
        if self._pinned is not None and not self._checked:
            actual = self.server_digest()
            if actual != self._pinned:
                raise LlmError(
                    f"Ollama model {self.model} has weights {actual}, the config pins "
                    f"{self._pinned}; pull the pinned model or update the config"
                )
            self._checked = True
        body = {
            "model": self.model,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "stream": False,
            "format": request.json_schema,
            "options": {
                "temperature": request.temperature,
                "seed": request.seed,
                "num_predict": request.max_tokens,
                "num_ctx": self.num_ctx,
            },
            "keep_alive": self.keep_alive,
        }
        started = time.perf_counter()
        data = self._call("POST", "/api/chat", body, timeout=self.timeout_s)
        latency = time.perf_counter() - started
        message = data.get("message") or {}
        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)
        if prompt_tokens >= self.num_ctx:
            raise RequestTooLarge(
                f"the prompt used the whole context ({prompt_tokens} of num_ctx {self.num_ctx} "
                "tokens); raise num_ctx"
            )
        return Reply(
            text=str(message.get("content") or ""),
            model=str(data.get("model") or self.model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_s=round(latency, 3),
            finish_reason=data.get("done_reason"),
            meta={
                name: round(int(data[field]) / 1e9, 3)
                for name, field in (
                    ("total_s", "total_duration"),
                    ("load_s", "load_duration"),
                    ("prompt_eval_s", "prompt_eval_duration"),
                    ("eval_s", "eval_duration"),
                )
                if isinstance(data.get(field), int)
            },
        )

    def _call(
        self, method: str, path: str, payload: dict[str, Any] | None, *, timeout: float
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        reply = self.transport(
            method,
            self.host + path,
            body=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        if reply.status != 200:
            raise LlmError(f"Ollama {path} returned HTTP {reply.status}: {reply.snippet()}")
        data = reply.json()
        if not isinstance(data, dict):
            raise LlmError(f"Ollama {path} returned {type(data).__name__}, expected an object")
        return data
