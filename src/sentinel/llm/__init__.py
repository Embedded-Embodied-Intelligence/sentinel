"""LLM layer (WP6): one client protocol over Ollama, Groq and a scripted fake, a record/replay
cache, JSON-schema-validated answers and versioned prompts (CLAUDE.md invariant 3; ADR-0018).

Only `sentinel.wbs`, `sentinel.experiments` and the interpretation layer import this package;
no simulation or rollout path calls an LLM.
"""

from sentinel.llm.cache import CACHE_MODES, DEFAULT_CACHE_DIR, CacheEntry, CacheMode, LlmCache
from sentinel.llm.client import BaseClient, ClientStats
from sentinel.llm.core import (
    CacheMiss,
    ErrorDetail,
    LlmClient,
    LlmError,
    LlmResponse,
    Message,
    OutputError,
    QuotaExhausted,
    Reply,
    Request,
    RequestTooLarge,
    backend_schema,
)
from sentinel.llm.fake import FakeLlmClient, FakeReply
from sentinel.llm.groq import GroqClient, TokenRateLimiter
from sentinel.llm.ollama import OllamaClient
from sentinel.llm.prompts import Prompt, load_prompt
from sentinel.llm.secrets import Secret, load_secret, load_setting

__all__ = [
    "CACHE_MODES",
    "DEFAULT_CACHE_DIR",
    "BaseClient",
    "CacheEntry",
    "CacheMiss",
    "CacheMode",
    "ClientStats",
    "ErrorDetail",
    "FakeLlmClient",
    "FakeReply",
    "GroqClient",
    "LlmCache",
    "LlmClient",
    "LlmError",
    "LlmResponse",
    "Message",
    "OllamaClient",
    "OutputError",
    "Prompt",
    "QuotaExhausted",
    "Reply",
    "Request",
    "RequestTooLarge",
    "Secret",
    "TokenRateLimiter",
    "backend_schema",
    "load_prompt",
    "load_secret",
    "load_setting",
]
