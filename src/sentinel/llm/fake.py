"""Scripted backend for tests and smoke runs: answers come from a list, in order, or from a
function of the conversation; token counts are estimated from the text."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sentinel.llm.cache import CacheMode, LlmCache
from sentinel.llm.client import BaseClient
from sentinel.llm.core import LlmError, Message, Reply, Request, estimate_tokens


@dataclass(frozen=True)
class FakeReply:
    """A scripted answer and the finish reason the backend reports with it."""

    text: str
    finish_reason: str = "stop"


Responder = Callable[[Sequence[Message]], "str | FakeReply"]


class FakeLlmClient(BaseClient):
    """An `LlmClient` without a model; `requests` records every backend call."""

    backend = "fake"

    def __init__(
        self,
        script: Sequence[str | FakeReply] | Responder,
        *,
        model: str = "scripted",
        latency_s: float = 0.0,
        cache: LlmCache | None = None,
        mode: CacheMode = "auto",
    ) -> None:
        super().__init__(model, cache=cache, mode=mode)
        self._responder = script if callable(script) else None
        self._script = list(script) if not callable(script) else []
        self.latency_s = latency_s
        self.requests: list[Request] = []

    def _send(self, request: Request) -> Reply:
        if self._responder is not None:
            answer = self._responder(request.messages)
        elif len(self.requests) < len(self._script):
            answer = self._script[len(self.requests)]
        else:
            raise LlmError(f"the fake script has only {len(self._script)} answers")
        self.requests.append(request)
        scripted = answer if isinstance(answer, FakeReply) else FakeReply(answer)
        return Reply(
            text=scripted.text,
            model=self.model,
            prompt_tokens=sum(estimate_tokens(message.content) for message in request.messages),
            completion_tokens=estimate_tokens(scripted.text),
            latency_s=self.latency_s,
            finish_reason=scripted.finish_reason,
        )
