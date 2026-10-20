# WP0 — Project scaffold, domain model, PSPLIB data

<context>
You are the implementer of the Sentinel project. Before writing code, read:
- `CLAUDE.md` (rules and invariants)
- `docs/spec/model.md` §1 (project instance, schedule feasibility, bounds)
- `docs/spec/architecture.md` (package layout, interfaces, data paths)
- `docs/workflow/wp-protocol.md` and the skill `.claude/skills/wp-report/SKILL.md`
- `tests/fixtures/README.md` (a hand-made instance with known LB0 = 7 and optimum = 7)

The repository currently contains only documentation, skills, `README.md`, `LICENSE`,
`.gitignore`, `.env.example` and `tests/fixtures/tiny.sm`. The server has uv 0.13.2 and a
uv-managed CPython 3.12. Verified facts about the `psplib` package (v0.4.0):
`psplib.parse(path, instance_format="psplib")` returns `ProjectInstance(resources, activities,
projects, skills)`; `Resource(capacity, renewable, skills)`; `Activity(modes, successors,
delays, optional, selection_groups, name)` with **0-based** successor indices;
`Mode(duration, demands, skill_requirements)`.

PSPLIB download URLs (verified):
- instances: `https://www.om-db.wi.tum.de/psplib/download_dataset.php?set={set}&mode=sm&format=zip`
- solutions: `https://www.om-db.wi.tum.de/psplib/download_solution.php?set={set}&mode=sm&type={type}`
  with `type ∈ {opt, hrs, lb}`; available: j30 → opt, hrs; j60 → hrs, lb.
</context>

<task>
1. **Scaffold with uv** (src layout, package `sentinel`, Python `>=3.12,<3.13`).
   - Runtime dependencies: `numpy>=2.1`, `pydantic>=2.10`, `ortools>=9.12`, `psplib>=0.4,<0.5`.
   - Dev dependency group: `pytest>=8`, `ruff>=0.8`, `mypy>=1.13`, `pre-commit>=4`,
     `detect-secrets>=1.5`.
   - Ruff: line length 100, rules `E,F,I,B,UP,SIM,RUF`; formatter enabled.
   - Mypy: `strict = true` for `src/`, pydantic plugin, `ignore_missing_imports` only for
     `ortools.*` and `psplib.*` if needed.
   - Pytest: `testpaths = ["tests"]`, register marker `data` (needs downloaded PSPLIB data).
   - Console script `sentinel = "sentinel.cli:main"`. Commit `uv.lock`.
2. **Pre-commit** (`.pre-commit-config.yaml`): prefer `repo: local` hooks that call `uv run`
   so versions match `uv.lock`: ruff check, ruff format check, detect-secrets with a committed
   `.secrets.baseline`; plus `check-added-large-files` (`--maxkb=5000`),
   `end-of-file-fixer`, `trailing-whitespace`, `check-toml`. Run `uv run pre-commit install`.
3. **Domain model** `src/sentinel/model/` implementing spec §1 and §1.3:
   - `instance.py`: frozen pydantic models `Role(id, name, capacity)`,
     `Worker(id, role, name)`, `Activity(id, duration, demands: tuple[int, ...],
     successors: tuple[int, ...], name="")`, `ProjectInstance(name, activities, roles,
     workers, deadline: int | None = None, budget: float | None = None, source: str | None = None)`.
     A model validator enforces every validity condition of §1. Helpers: `n_activities`,
     `n_real`, `source_id`, `sink_id`, `predecessors(j)`, `topological_order()`.
     Factory `make_workers(roles)` creates one worker per capacity unit (§1.1).
   - `schedule.py`: frozen `Schedule(starts: tuple[int, ...])` indexed by activity id, with
     `finish(instance, j)` and `makespan(instance)`; frozen `Violation(kind, detail,
     activity=None, time=None, role=None)` with `kind` in
     `{"length", "source_start", "negative_start", "precedence", "resource"}`;
     `validate_schedule(instance, schedule) -> list[Violation]` (empty = feasible, §1.3).
4. **Bounds** `src/sentinel/scheduling/bounds.py` (spec §1.4): `earliest_starts`,
   `latest_finishes(instance, horizon=None)`, `latest_starts(instance, horizon=None)`,
   `critical_path_lower_bound` (LB0). Pure functions over the topological order.
5. **Data** `src/sentinel/data/`:
   - `psplib_loader.py`: `load_psplib(path, name=None) -> ProjectInstance` (§1.1; reject
     multi-mode or non-renewable resources with a clear `ValueError`), `instance_path(set,
     instance, root)`, `list_instances(set, root) -> list[str]` (sorted naturally:
     `j301_1, j301_2, …, j3010_1`).
   - `reference.py`: parse PSPLIB solution files into `dict[str, int]` keyed like
     `"j30/j301_1"`. First inspect the downloaded files (`head -40`) to learn their exact
     layout, parse robustly (skip headers, parameter `Par` + instance `Inst` → name
     `j{n}{par}_{inst}`), and document the format in `docs/notes/WP0.md`.
     Provide `load_reference(set, kind, root) -> dict[str, int]`.
6. **Fetch script** `scripts/fetch_psplib.py --sets j30 j60 [--root data/psplib] [--force]`:
   stdlib only (`urllib.request` with a User-Agent header, timeouts, 3 retries); extracts
   `.sm` files to `data/psplib/<set>/`, saves solutions to
   `data/psplib/solutions/<set>_<type>.sm`, writes `data/psplib/MANIFEST.json` (URL, UTC
   time, SHA-256, file counts). Idempotent: skips existing files unless `--force`.
7. **CLI** `src/sentinel/cli.py` (argparse): `sentinel inspect j30/j301_1` and
   `sentinel inspect --file tests/fixtures/tiny.sm` print: name, real activities, roles with
   capacities, total duration, LB0, and reference makespans if available (opt / hrs / lb).
8. **Tests** (`tests/`):
   - fixture `tiny.sm`: loads with 5 activities, 1 role of capacity 3, 3 workers; LB0 = 7;
     topological order valid; schedule `starts=(0,0,3,3,7)` is feasible.
   - validator: detects a precedence violation, a resource overload (report day and role),
     negative start, wrong length; cycle and demand > capacity are rejected at construction.
   - `@pytest.mark.data` tests (skip cleanly if `data/psplib` is missing): all 480 J30
     instances load with 30 real activities and 4 roles; J60 loads 480 instances with 60
     real activities; reference J30 opt has 480 entries and every `opt ≥ LB0`; J60
     `hrs ≥ lb` for every instance present in both files.
9. Run the fetch script once, run all checks, then finish with the `wp-report` skill
   (report, notes including the solution-file format, roadmap update, commit, push).
</task>

<constraints>
- No scheduling algorithms beyond CPM bounds (SGS and CP-SAT are WP1). No simulation.
- Do not edit `docs/spec/`, `CLAUDE.md`, `LICENSE` or existing ADRs.
- Tests never use the network. Data under `data/` is never committed.
- No dependencies beyond the lists above without recording a decision in the report.
- Keep terminal output short; do not print whole data files.
</constraints>

<acceptance_criteria>
1. `uv sync` succeeds and `uv.lock` is committed.
2. Quality gate passes: `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run mypy src`, `uv run pytest -q`.
3. `uv run python scripts/fetch_psplib.py --sets j30 j60` completes; `data/psplib/j30` and
   `data/psplib/j60` each contain 480 `.sm` files; the four solution files exist.
4. `uv run pytest -q -m data` runs the data tests and they pass (not skipped).
5. `uv run sentinel inspect --file tests/fixtures/tiny.sm` prints LB0 = 7.
6. `uv run sentinel inspect j30/j301_1` prints LB0 and the optimal makespan, with opt ≥ LB0.
7. `uv run pre-commit run --all-files` passes.
8. `git status` is clean after the final commit; no file under `data/` or `.env` is tracked
   (`git ls-files | grep -E '^data/|\.env$'` prints nothing).
</acceptance_criteria>

<report_format>
Use the `wp-report` skill: `docs/reports/WP0.md` with all required sections. In "Numbers"
include: install time, test counts, download sizes, load time for all J30 instances, and the
output of acceptance checks 5 and 6.
</report_format>
