"""Build and write a cockpit (WP8; ADR-0021): the options of `sentinel dashboard`, the world
and its two runs, the explanations and the provenance, then the page (`page.render`).

The output is deterministic: the page holds the commit and the package versions but no time,
and every number comes from the seeded runs, so the same command at the same commit writes the
same bytes.
"""

import platform
import shlex
from dataclasses import dataclass, field, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sentinel.dashboard.assemble import (
    DayEvents,
    Kpis,
    LogRow,
    Row,
    day_events,
    decision_log,
    gantt_rows,
    kpis,
)
from sentinel.dashboard.explain import (
    LLM_BACKENDS,
    LlmExplainer,
    Shown,
    explained_by_llm,
    shown_template,
)
from sentinel.dashboard.labels import Language
from sentinel.dashboard.world import (
    Catalogue,
    CockpitError,
    Forecast,
    PolicyRun,
    World,
    build_world,
    forecasts,
    load_catalogue,
    run,
)
from sentinel.experiments.runs import git_state

EXPLAIN_MODES = ("template", *LLM_BACKENDS)
MAX_BYTES = 2_000_000  # the page's size limit (WP8)
GIT_EXCLUDE = ("results", "paper/generated", "docs/dashboard")  # generated outputs
VERSIONED = ("numpy", "ortools", "pydantic")


@dataclass(frozen=True)
class Options:
    """What `sentinel dashboard` simulates and how it writes it; `root` and `cache` replace the
    PSPLIB data root and the baseline plan cache of the world config."""

    set_name: str
    instance: str
    replication: int = 0
    lambda_a: float = 0.01
    delta_d: float | None = None
    policy: str = "sentinel_full"
    compare: str = "no_reaction"
    explain: str = "template"
    language: Language = "en"
    root: Path | None = None
    cache: Path | None = None

    def command(self, out: Path | None) -> str:
        """The command line that writes this cockpit again."""
        args = [
            "uv run sentinel dashboard",
            f"--set {self.set_name}",
            f"--instance {self.instance}",
            f"--replication {self.replication}",
            f"--lambda-a {self.lambda_a:g}",
        ]
        if self.delta_d is not None:
            args.append(f"--delta-d {self.delta_d:g}")
        args += [f"--policy {self.policy}", f"--compare {self.compare}"]
        if self.explain != "template":
            args.append(f"--explain {self.explain}")
        if self.language != "en":
            args.append(f"--lang {self.language}")
        if self.root is not None:
            args.append(f"--root {shlex.quote(self.root.as_posix())}")
        if self.cache is not None:
            args.append(f"--cache {shlex.quote(self.cache.as_posix())}")
        if out is not None:
            args.append(f"--out {shlex.quote(out.as_posix())}")
        return " ".join(args)


@dataclass(frozen=True)
class Provenance:
    """The code state and the software that produced a cockpit, and its command."""

    commit: str | None
    dirty: bool | None
    software: tuple[tuple[str, str], ...]
    command: str


def provenance(command: str) -> Provenance:
    git = git_state(GIT_EXCLUDE)
    software = [("Python", platform.python_version())]
    for name in VERSIONED:
        try:
            software.append((name, version(name)))
        except PackageNotFoundError:  # pragma: no cover - installed with the project
            software.append((name, "?"))
    return Provenance(git["commit"], git["dirty"], tuple(software), command)


@dataclass(frozen=True)
class Side:
    """One policy of the cockpit: its run, KPIs, Gantt rows and the events of its world."""

    run: PolicyRun
    kpis: Kpis
    rows: tuple[Row, ...]
    events: tuple[DayEvents, ...]


@dataclass(frozen=True)
class Cockpit:
    """Everything the page shows: the world, both policies, the primary policy's forecasts and
    decision log with one explanation per row, how explanations were made, and the provenance."""

    options: Options
    world: World
    first: Side
    second: Side
    forecasts: tuple[Forecast, ...]
    log: tuple[LogRow, ...]
    explanations: tuple[Shown, ...]
    explain_source: str
    provenance: Provenance
    catalogue: Catalogue = field(repr=False)
    out: Path | None = None


def build(
    options: Options,
    *,
    out: Path | None = None,
    catalogue: Catalogue | None = None,
    explainer: LlmExplainer | None = None,
) -> Cockpit:
    """Simulate both policies and assemble the cockpit; `explainer` replaces the LLM explainer
    of `options.explain` (tests)."""
    if options.explain not in EXPLAIN_MODES:
        raise ValueError(f"unknown --explain {options.explain!r}; known: {EXPLAIN_MODES}")
    catalogue = load_catalogue() if catalogue is None else catalogue
    world = build_world(
        catalogue,
        options.set_name,
        options.instance,
        replication=options.replication,
        lambda_a=options.lambda_a,
        delta_d=options.delta_d,
        policies=(options.policy, options.compare),
        root=options.root,
        cache=options.cache,
    )
    sides = []
    for name in (options.policy, options.compare):
        policy_run = run(world, catalogue, name)
        result = policy_run.result
        sides.append(
            Side(
                policy_run,
                kpis(world, policy_run),
                tuple(gantt_rows(world, result)),
                tuple(day_events(result)),
            )
        )
    first, second = sides
    log = tuple(decision_log(world, first.run)) if first.run.is_sentinel else ()
    if options.explain != "template" and explainer is None:
        explainer = LlmExplainer(options.explain)
    cockpit = Cockpit(
        options=options,
        world=world,
        first=first,
        second=second,
        forecasts=tuple(forecasts(world, first.run)),
        log=log,
        explanations=(),
        explain_source="template",
        provenance=provenance(options.command(out)),
        catalogue=catalogue,
        out=out,
    )
    return explained(cockpit, explainer)


def explained(
    cockpit: Cockpit, explainer: LlmExplainer | None, language: Language | None = None
) -> Cockpit:
    """The cockpit with an explanation per log row: by `explainer` (an LLM) for the
    deliberations that passed the needs gate, from the template otherwise, in `language`
    (default: the options'), which also becomes the page's language."""
    backend = "template" if explainer is None else explainer.backend
    options = replace(cockpit.options, explain=backend)
    if language is not None:
        options = replace(options, language=language)
    world, first = cockpit.world, cockpit.first
    keys = (world.name, str(world.replication), f"{world.lambda_a:g}", options.policy)
    shown = []
    for row in cockpit.log:
        record = row.record
        if explainer is not None and explained_by_llm(record):
            observation = first.run.observations[row.day]
            shown.append(explainer(record, observation, first.run.params, *keys))
        else:
            shown.append(shown_template(record, options.language))
    source = "template"
    if explainer is not None:
        source = f"{explainer.backend}|{explainer.model}|{explainer.cache_file.as_posix()}"
    command = options.command(cockpit.out)
    return replace(
        cockpit,
        options=options,
        explanations=tuple(shown),
        explain_source=source,
        provenance=replace(cockpit.provenance, command=command),
    )


def write(
    options: Options,
    out: Path,
    *,
    catalogue: Catalogue | None = None,
    explainer: LlmExplainer | None = None,
) -> tuple[Path, Cockpit]:
    """Build the cockpit, render it and write it to `out` (refusing a page over 2 MB)."""
    cockpit = build(options, out=out, catalogue=catalogue, explainer=explainer)
    return save(cockpit, out), cockpit


def save(cockpit: Cockpit, out: Path) -> Path:
    """Render a built cockpit and write it to `out` (refusing a page over 2 MB)."""
    # Imported here so that the data modules do not depend on the page.
    from sentinel.dashboard.page import render

    data = render(cockpit).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise CockpitError(f"the cockpit has {len(data)} bytes, more than {MAX_BYTES}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out
