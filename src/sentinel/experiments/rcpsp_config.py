"""Validated configuration of the RCPSP benchmark runner (e.g. configs/wp1_rq2.toml)."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from sentinel.data.reference import ReferenceKind
from sentinel.scheduling.priority_rules import RuleName


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SetConfig(_Frozen):
    """An instance set and its reference makespans; `dev_lb0` adds the LB0 deviation to tables."""

    name: str = Field(min_length=1)
    reference: ReferenceKind
    dev_lb0: bool = False


class _MethodBase(_Frozen):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)


class SgsMethod(_MethodBase):
    """One serial SGS pass with a priority rule."""

    kind: Literal["sgs"]
    rule: RuleName


class RbrsMethod(_MethodBase):
    """Regret-based biased random sampling on LFT with a schedule budget."""

    kind: Literal["rbrs"]
    n_schedules: PositiveInt
    alpha: float = Field(default=1.0, allow_inf_nan=False)


class CpsatMethod(_MethodBase):
    """CP-SAT with a wall-clock time limit."""

    kind: Literal["cpsat"]
    time_limit_s: PositiveFloat
    num_workers: PositiveInt = 1


Method = Annotated[SgsMethod | RbrsMethod | CpsatMethod, Field(discriminator="kind")]


class BenchmarkConfig(_Frozen):
    """Seeds, parallelism, data root, instance sets and methods (methods in table order)."""

    name: str = Field(min_length=1)
    base_seed: NonNegativeInt
    max_workers: PositiveInt
    data_root: Path
    sets: tuple[SetConfig, ...] = Field(min_length=1)
    methods: tuple[Method, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_unique_names(self) -> Self:
        for kind, names in (
            ("set", [s.name for s in self.sets]),
            ("method", [m.name for m in self.methods]),
        ):
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                raise ValueError(f"duplicate {kind} names: {duplicates}")
        return self
