"""Editing a person's text for an audience, role 4 of the interpretation layer ("redakcja";
spec section 11.9, ADR-0038).

The model is given the person's text and the style of one audience and answers in the schema
`Redaction`: the edited text only, nothing else; it has no tools, and its answer enters nothing
but the page that shows it beside the original. What it changed is computed by code
(`sentinel.interpret.tracked`), and whether the facts survived by the fact guard
(`sentinel.interpret.facts`); the model is never asked to report its changes in the
application. The RQ6 study also asks for the list of changes (`RedactionWithChanges`, the format
`redact_format_changes`) to measure whether a model's own account of its edits can be trusted.
Prompts are English and versioned; the text is edited in its own language.
"""

from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PositiveInt

from sentinel.llm import LlmClient, LlmResponse, Message, load_prompt

REDACT_PROMPT = "redact"  # system prompt, prompts/redact.<version>.txt
FORMAT_PROMPT = "redact_format"  # the edited text only
FORMAT_CHANGES_PROMPT = "redact_format_changes"  # the text and the model's list of changes
STYLE_PROMPT = "redact_style_{audience}"  # one style per audience
Audience = Literal["edit", "board", "finance", "team", "summary"]
AUDIENCES: tuple[Audience, ...] = ("edit", "board", "finance", "team", "summary")
REPORT_AUDIENCES: tuple[Audience, ...] = ("edit", "board", "finance", "team")  # Raporty's chips
LANGUAGE_NAMES = {"pl": "Polish", "en": "English"}
MAX_CHARS = 20_000  # the longest text a person may give (about seven pages)


class RedactSettings(BaseModel):
    """Prompt version and decoding parameters of an editing call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(default="v1", min_length=1)
    max_tokens: PositiveInt = 8192
    temperature: float = Field(default=0.0, ge=0, allow_inf_nan=False)


def _bounded(limit: int) -> Callable[[str], str]:
    """A length check in code: a `maxLength` in the schema would become a grammar of that many
    repetitions for a local model (Ollama cannot build it)."""

    def check(value: str) -> str:
        if len(value) > limit:
            raise ValueError(f"longer than {limit} characters")
        return value

    return check


Text = Annotated[str, AfterValidator(_bounded(2 * MAX_CHARS))]


class Redaction(BaseModel):
    """The answer of an editing call: the edited text, paragraphs separated by a blank line."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: Text = Field(min_length=1)


class ReportedChange(BaseModel):
    """A change as the model reports it (RQ6 only): its words before and after."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    before: Text
    after: Text


class RedactionWithChanges(Redaction):
    """The RQ6 answer: the edited text and the model's own list of its changes."""

    changes: list[ReportedChange]


def redact_messages(
    text: str,
    audience: Audience,
    language: str,
    version: str = "v1",
    *,
    report_changes: bool = False,
) -> list[Message]:
    """The conversation of an editing call: the system prompt with the audience's style and the
    answer's format, and the person's text."""
    system = load_prompt(REDACT_PROMPT, version)
    style = load_prompt(STYLE_PROMPT.format(audience=audience), version)
    answer = load_prompt(FORMAT_CHANGES_PROMPT if report_changes else FORMAT_PROMPT, version)
    content = system.render(
        language=LANGUAGE_NAMES.get(language, language), style=style.text, format=answer.text
    )
    return [Message(role="system", content=content), Message(role="user", content=text)]


def redact(
    client: LlmClient,
    text: str,
    audience: Audience,
    *,
    language: str,
    seed: int,
    settings: RedactSettings,
) -> LlmResponse[Redaction]:
    """One editing call: the person's text edited for `audience`."""
    return client.complete(
        redact_messages(text, audience, language, settings.prompt_version),
        schema=Redaction,
        temperature=settings.temperature,
        seed=seed,
        max_tokens=settings.max_tokens,
    )


def redact_reporting(
    client: LlmClient,
    text: str,
    audience: Audience,
    *,
    language: str,
    seed: int,
    settings: RedactSettings,
) -> LlmResponse[RedactionWithChanges]:
    """The RQ6 variant: the edited text and the model's list of its changes."""
    return client.complete(
        redact_messages(text, audience, language, settings.prompt_version, report_changes=True),
        schema=RedactionWithChanges,
        temperature=settings.temperature,
        seed=seed,
        max_tokens=settings.max_tokens,
    )
