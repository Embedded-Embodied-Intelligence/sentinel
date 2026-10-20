# WP0 report — Project scaffold, domain model, PSPLIB data

- Date: 2026-10-20
- Commit(s): 286d51a (code, config, tests); the report/notes/roadmap commit follows it

## Summary
The repository is now a uv project (`sentinel`, Python 3.12) with ruff, strict mypy, pytest and
pre-commit (ruff, detect-secrets, hygiene hooks). The domain model of spec §1 (frozen pydantic
`ProjectInstance` with all validity checks, `Schedule`, `validate_schedule`) and the CPM bounds of
§1.4 are implemented and tested. PSPLIB J30/J60 instances and the four reference-solution files
are fetched reproducibly, load into the model (960 instances in under 1 s), and
`sentinel inspect` prints an instance summary with LB0 and reference makespans.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | `uv sync` succeeds, `uv.lock` committed | `uv sync`; `uv lock --check` | PASS (42 packages; lock up to date; committed in 286d51a) |
| 2 | Quality gate | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q` | PASS (ruff clean; 42 files formatted; mypy: no issues in 10 files; 67 passed) |
| 3 | Fetch completes; 480 + 480 `.sm`; four solution files | `uv run python scripts/fetch_psplib.py --sets j30 j60` | PASS (2.0 s; j30 480, j60 480; j30_opt, j30_hrs, j60_hrs, j60_lb; re-run skips everything, manifest unchanged) |
| 4 | Data tests run and pass, not skipped | `uv run pytest -q -m data` | PASS (5 passed, 62 deselected, 0 skipped) |
| 5 | Tiny fixture: LB0 = 7 | `uv run sentinel inspect --file tests/fixtures/tiny.sm` | PASS (`LB0: 7`, output below) |
| 6 | j301_1: LB0 and optimum, opt ≥ LB0 | `uv run sentinel inspect j30/j301_1` | PASS (`LB0: 38`, `opt=43`, output below) |
| 7 | pre-commit passes | `uv run pre-commit run --all-files` | PASS (all 7 hooks passed) |
| 8 | Clean tree; no `data/` or `.env` tracked | `git status --short`; `git ls-files \| grep -E '^data/\|\.env$'` | PASS after 286d51a (both empty); re-checked after the report commit |

## Changes
- Tooling: `pyproject.toml` (deps, dev group, ruff/mypy/pytest config, console script), `uv.lock`,
  `.python-version`, `.pre-commit-config.yaml`, `.secrets.baseline`; `README.md` quick start.
- `sentinel.model`: `instance.py` (Role, Worker, Activity, ProjectInstance, make_workers),
  `schedule.py` (Schedule, Violation, validate_schedule), `__init__.py` (re-exports).
- `sentinel.scheduling`: `bounds.py` (earliest_starts, latest_finishes, latest_starts,
  critical_path_lower_bound).
- `sentinel.data`: `psplib_loader.py` (load_psplib, instance_path, list_instances, natural_key),
  `reference.py` (parse_reference, load_reference, reference_path).
- `sentinel`: `cli.py` (`sentinel inspect`).
- `scripts/fetch_psplib.py`: stdlib downloader with retries, atomic writes, `MANIFEST.json`.
- `tests/`: `conftest.py` and 8 test modules (67 tests; 5 marked `data`).
- Docs: `docs/reports/WP0.md`, `docs/notes/WP0.md`, `docs/roadmap.md` (WP0 done).

## Decisions
- Build backend `uv_build>=0.12.2,<0.14`: uv's own backend; the bound from `uv init` (`<0.13`) is
  widened so both uv 0.12.2 (this Mac) and 0.13.2 (server) use their built-in backend.
- Mypy `ignore_missing_imports` only for `psplib.*` (no `py.typed`); ortools is not imported yet.
- `R_k` = number of workers of role `k` (definition in §1) is enforced at construction, together
  with positional ids (`activities[j].id == j`) and a ban on duplicate successors.
- Predecessors and the topological order are computed once in the validator (Kahn 1962, smallest
  ready id first: deterministic) and kept in private attributes of the frozen model.
- Reachability is checked by degrees: in a DAG where 0 is the only activity without predecessors
  and n+1 the only one without successors, every activity lies on a 0→n+1 path.
- `Schedule.makespan` returns `S_{n+1}` exactly as §1.3 defines `C`; `finish`/`makespan` raise
  on a length mismatch.
- `validate_schedule`: a length mismatch is reported alone; overloads are reported per
  (role, day) by an event sweep (cost independent of the time span), `detail` names the running
  activities; `S_0 < 0` yields both `source_start` and `negative_start`.
- `latest_finishes` accepts any horizon; `T < LB0` gives negative slack (useful for urgency in §5).
- Loader: default name `<parent dir>/<stem>` (gives `j30/j301_1`; the fixture becomes
  `fixtures/tiny`), `source="psplib"`, workers named `R1-0, R1-1, …`.
- Solution files: a data line is any line starting with three integers (value may carry `*`);
  another line starting with two integers is an error, so format changes cannot drop entries.
- Fetch script: staging directory + rename (instances) and `.part` + replace (solutions) make
  writes atomic; besides the archive SHA-256 it records a content hash of the extracted files;
  `--sets` limited to the verified sets j30, j60; manifest rewritten only when it changes.
- `uv.lock` is scanned by detect-secrets (no findings; would catch credentials in index URLs).
- pytest runs with `--strict-markers -ra` so skip reasons are always visible.
- ADRs created: none (all choices are local; reasons are recorded here and in the notes).

## Deviations
- Machine: run on a MacBook Pro (Apple M1, 8 cores, 8 GB RAM, macOS 26.6.2) with uv 0.12.2
  (Homebrew), not on the server (WSL2, uv 0.13.2). The lock file is universal; verification on
  the server is listed below. Only shell usage differed (`cat -vet` instead of `cat -A`).
- `instance_path`, `list_instances`, `load_reference` name their first parameter `set_name`
  instead of `set` (no shadowing of the builtin); positional calls as in the WP are unchanged.
- `docs/spec/architecture.md` names the helper `n_real_activities`; the WP prompt says `n_real`,
  which is implemented (docs/spec not edited).
- Small additions not listed in the WP: `reference_path`, `parse_reference`, `natural_key`,
  `ViolationKind`, offline tests of the fetch script, README quick start. No new dependencies.

## Spec questions
- May a real activity have `p_j = 0`? §1 says `p_j ∈ ℕ` and the notation uses `t ∈ ℕ` from 0,
  so 0 is accepted (marked `SPEC-Q` in `model/instance.py`). No effect on PSPLIB (real durations
  1–10); §2.1 turns such activities into `P_j ≥ 1` anyway. Suggest stating `p_j ≥ 1` for real
  activities in §1 if that is intended.

## Numbers
| Measurement | Value |
| --- | --- |
| `uv sync`, first run in the repo (resolve + install 42 packages) | 2.2 s |
| `uv sync --frozen` into a fresh env, cold (`--no-cache`, all downloads) | 3.9 s |
| `uv sync --frozen` into a fresh env, warm uv cache | 0.35 s |
| `.venv` size | 258 MB |
| Tests | 67 passed in 0.96 s (62 offline + 5 data); without data: 62 passed, 5 skipped |
| `pytest -m data` | 5 passed, 62 deselected in 0.84 s |
| Fetch, first run (2 archives + 4 solution files) | 2.0 s wall |
| Download sizes | j30.zip 458,761 B; j60.zip 657,002 B; j30_opt 16,199 B; j30_hrs 33,465 B; j60_hrs 32,360 B; j60_lb 11,844 B (total 1.21 MB) |
| Extracted data on disk | 5.7 MB (`du`; 960 `.sm` files) |
| Load all 480 J30 instances (`load_psplib`) | 0.25 s (0.52 ms each; `psplib.parse` 0.06 s of it) |
| Load all 480 J60 instances | 0.52 s |
| LB0 for all 480 J30 instances | 4 ms |
| `pre-commit run --all-files`, first run (hook env install) | 6.5 s |

Environment: Apple M1 (4P + 4E cores), 8 GB RAM, macOS 26.6.2, uv 0.12.2, CPython 3.12.13
(uv-managed), git 2.56.0. Resolved: numpy 2.5.4, pydantic 2.14.1, ortools 9.15.6755,
psplib 0.4.0 (pandas 3.0.6, protobuf 6.33.6 via ortools); pytest 9.1.1, ruff 0.17.1, mypy 2.4.0,
pre-commit 4.7.0, detect-secrets 1.5.0, pre-commit-hooks v6.0.0. Timings are from this laptop,
not the experiment server.

Acceptance check 5:
```
name:            fixtures/tiny
file:            tests/fixtures/tiny.sm
real activities: 3
roles:           R1=3 (3 workers)
total duration:  9
LB0:             7
reference:       none
```

Acceptance check 6:
```
name:            j30/j301_1
file:            data/psplib/j30/j301_1.sm
real activities: 30
roles:           R1=12, R2=13, R3=4, R4=12 (41 workers)
total duration:  158
LB0:             38
reference:       opt=43, hrs=43
```

## Commands for the owner
On the server, to confirm the lock and the data match this run (under 1 minute, no tmux needed):
```bash
cd ~/projects/sentinel && git pull
uv sync --locked            # must not need to change uv.lock (created with uv 0.12.2)
uv run pre-commit install   # git hooks are per clone
uv run python scripts/fetch_psplib.py --sets j30 j60
uv run pytest -q            # expect 67 passed
grep content_sha256 data/psplib/MANIFEST.json  # expect b77624e1… (j30), 8d9894ce… (j60)
```

## Open issues / next steps
- WP1: add `ortools.*` to the mypy override (ortools 9.15 ships no `py.typed`).
- `j60_lb.sm` has no entries for Par 42–48 (70 instances) and no `*` markers despite its header;
  proven J60 optima are the 382 instances with `hrs = lb`. WP1 uses `hrs` and LB0, so no impact.
- Architect: decide the `p_j = 0` spec question and the `n_real` / `n_real_activities` naming.
- Server check of `uv sync --locked` and data checksums (commands above).
