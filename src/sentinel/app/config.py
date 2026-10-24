"""Configuration of `sentinel ui` (WP9a; ADR-0024): where the data live, how many background
workers run, and the limits of the demo mode, read from a TOML file (`configs/app_demo.toml`)."""

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from sentinel.data.psplib_loader import DEFAULT_ROOT
from sentinel.simulation.baselines import DEFAULT_CACHE_ROOT

DEMO_CONFIG = Path("configs/app_demo.toml")


def default_data_dir() -> Path:
    """$XDG_DATA_HOME/sentinel, else ~/.local/share/sentinel: outside the repository."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "sentinel"


class Limits(BaseModel):
    """Limits per demo session (None: no limit) and of the whole server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    projects_per_session: PositiveInt | None = None
    tasks_per_project: PositiveInt | None = None
    simulator_days: PositiveInt | None = None  # days per advance
    concurrent_jobs: PositiveInt | None = None  # per session
    requests_per_minute: PositiveInt | None = None  # per client address
    upload_kb: PositiveInt = 5120
    llm_calls_per_day: int | None = Field(default=None, ge=0)  # server-wide
    sandbox_hours: float = Field(default=24.0, gt=0)


class AppConfig(BaseModel):
    """The application's settings; `inline_jobs` runs jobs in the request (tests)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_dir: Path = Field(default_factory=default_data_dir)
    demo: bool = False
    workers: PositiveInt = 1
    limits: Limits = Limits()
    secure_cookies: bool = False
    trust_proxy: bool = False
    llm: Literal["on", "capped", "off"] = "on"
    showcase: bool = True
    psplib_root: Path = DEFAULT_ROOT
    baseline_cache: Path = DEFAULT_CACHE_ROOT
    inline_jobs: bool = False

    @property
    def database(self) -> Path:
        return self.data_dir / "sentinel.db"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def secret_file(self) -> Path:
        return self.data_dir / "secret.key"

    @property
    def llm_cache(self) -> Path:
        return self.data_dir / "llm_cache"


def load_config(path: Path | None, **overrides: object) -> AppConfig:
    """The config of a TOML file (none: the defaults) with command-line overrides."""
    values: dict[str, object] = {}
    if path is not None:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
    values.update({key: value for key, value in overrides.items() if value is not None})
    return AppConfig.model_validate(values)
