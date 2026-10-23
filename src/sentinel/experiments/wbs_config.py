"""Validated configuration of the RQ1 WBS extraction study (configs/wp6_rq1.toml; WP6a)."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from sentinel.llm import DEFAULT_CACHE_DIR
from sentinel.wbs.extract import ExtractionSettings
from sentinel.wbs.narrate import Style
from sentinel.wbs.score import CpsatSettings


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SetConfig(_Frozen):
    """An instance set; every `stride`-th instance in natural order is used."""

    name: str = Field(min_length=1)
    stride: PositiveInt = 1


class OllamaBackend(_Frozen):
    """Local Ollama model; `digest` pins the weights (`sha256:<hex>` from `/api/show`)."""

    kind: Literal["ollama"]
    model: str = Field(min_length=1)
    digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    num_ctx: PositiveInt
    keep_alive: str = "30m"
    timeout_s: PositiveFloat = 1800.0


class GroqBackend(_Frozen):
    """Groq model; `options` are extra request fields (e.g. `reasoning_effort`), part of the
    cache key; `tokens_per_day` only enters the duration estimate."""

    kind: Literal["groq"]
    model: str = Field(min_length=1)
    tokens_per_minute: PositiveInt | None
    tokens_per_day: PositiveInt | None = None
    response_format: Literal["json_schema", "json_object"] = "json_schema"
    options: dict[str, JsonValue] = Field(default_factory=dict)
    max_wait_s: PositiveFloat = 900.0
    max_retries: NonNegativeInt = 6
    timeout_s: PositiveFloat = 300.0


class FakeBackend(_Frozen):
    """The scripted oracle of smoke runs: the template parser's reading of the description with
    seeded mistakes in the first 0..`max_faulty_rounds` answers of a session."""

    kind: Literal["fake"]
    model: str = "oracle"
    max_faulty_rounds: NonNegativeInt = 2


Backend = Annotated[OllamaBackend | GroqBackend | FakeBackend, Field(discriminator="kind")]


class SummarySettings(_Frozen):
    """Bootstrap of the paired differences and the names of the table and figure."""

    bootstrap_resamples: PositiveInt = 2000
    bootstrap_seed: NonNegativeInt = 2026
    table: str = Field(default="table_wp6_rq1", min_length=1)
    figure: str = Field(default="fig_wp6_rq1", min_length=1)


class WbsStudyConfig(_Frozen):
    """Seeds, instances, styles, backends, extraction and CP-SAT settings of the RQ1 study.
    `backends` is the study's backends in table order; `backend` holds the settings of every
    backend a run may select, the fake one of the smoke runs included."""

    name: str = Field(min_length=1)
    base_seed: NonNegativeInt
    narrator_seed: NonNegativeInt
    data_root: Path
    cache_dir: Path = DEFAULT_CACHE_DIR
    sets: tuple[SetConfig, ...] = Field(min_length=1)
    styles: tuple[Style, ...] = Field(min_length=1)
    backends: tuple[str, ...] = Field(min_length=1)
    backend: dict[str, Backend]
    extraction: ExtractionSettings
    cpsat: CpsatSettings = CpsatSettings()
    summary: SummarySettings = SummarySettings()

    @model_validator(mode="after")
    def _check_names(self) -> Self:
        for kind, names in (
            ("set", [s.name for s in self.sets]),
            ("style", [str(style) for style in self.styles]),
            ("backend", list(self.backends)),
        ):
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                raise ValueError(f"duplicate {kind} names: {duplicates}")
        unknown = [name for name in self.backends if name not in self.backend]
        if unknown:
            raise ValueError(f"backends without settings in [backend.*]: {unknown}")
        return self
