"""Record the model's answers to the "Próba ataku" sample, for the replay the application shows
by default (docs/design/v3-spec.md, section 4; WP19).

Usage:
  uv run python scripts/record_attack.py [--provider openrouter] [--model openai/gpt-oss-120b]

The sample of `sentinel.app.attack` goes through the application's real message flow once per
language with the configured cloud model; every answer the reader received (the first and any
repair round's) is written in order to src/sentinel/app/attack_replay.json, with no prompt and
no key. The key comes from the environment or `.env` (OPENROUTER_API_KEY or GROQ_API_KEY) and
is never printed. No cache is written: a recording is a live call. Cost: a few thousand tokens
per language (well under 0.01 USD for gpt-oss-120b).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel

from sentinel.app.attack import REPLAY_PATH, run
from sentinel.app.llm import DEFAULT_MODELS, LlmSettings, make_client
from sentinel.app.models import Language
from sentinel.llm import DomainValidator, LlmClient, LlmResponse, Message
from sentinel.llm.secrets import load_secret

KEYS = {"openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY"}  # pragma: allowlist secret


class Capture:
    """An `LlmClient` that keeps the text of every answer it passes on."""

    def __init__(self, inner: LlmClient) -> None:
        self.inner = inner
        self.answers: list[str] = []

    def complete[ModelT: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        schema: type[ModelT],
        temperature: float = 0.0,
        seed: int,
        max_tokens: int,
        validator: DomainValidator | None = None,
    ) -> LlmResponse[ModelT]:
        response = self.inner.complete(
            messages,
            schema=schema,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
            validator=validator,
        )
        self.answers.append(response.text)
        return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=sorted(KEYS), default="openrouter")
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)
    key = load_secret(KEYS[args.provider])
    if key is None:
        print(f"{KEYS[args.provider]} is not set", file=sys.stderr)
        return 1
    model = args.model or DEFAULT_MODELS[args.provider]
    settings = LlmSettings(provider=args.provider, model=model, api_key=key.reveal())
    languages: dict[str, dict[str, object]] = {}
    language: Language
    for language in ("pl", "en"):
        capture = Capture(make_client(settings, None))
        outcome = run(capture, language, recorded=False)
        languages[language] = {"answers": capture.answers}
        print(
            f"{language}: {len(capture.answers)} answer(s), valid={outcome.valid}, "
            f"instruction ignored={outcome.ignored}"
        )
    recording = {
        "provider": args.provider,
        "model": model,
        "recorded_on": date.today().isoformat(),
        "note": "answers of the model to the sample of sentinel.app.attack, in order; no prompt",
        "languages": languages,
    }
    REPLAY_PATH.write_text(json.dumps(recording, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"wrote {REPLAY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
