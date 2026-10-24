# WP7 report — paper artifacts from committed results, RQ1 error analysis, reproduce command

- Date: 2026-10-24
- Commit(s): f41d711 (`docs: WP6 done; invariant 3; cache privacy for invalid replies`), 238ac99
  (RQ1 error analysis), 8e0f9f3 (RQ1 summary regenerated), d07a099 (paper generator, reproduce
  command), 2b48630 (policy summaries regenerated), 1ee6391 (`paper/generated/`), 79f9309
  (README, limitations), 586af31 (relative paths in `MANIFEST.json`); the report commit
  follows them

## Summary
Every number, table and figure the article and the course report will cite now comes from the
14 committed runs: `sentinel paper` writes 1,430 LaTeX macros (each after a comment naming its
summary cell), five tables and six figures, in English and Polish, into `paper/generated/`, and
refuses a run that is dirty, a smoke run, incomplete or tampered. `sentinel reproduce --check`
regenerates all 117 summary and paper files without recomputation and finds them byte-identical;
`--commands` prints how to recompute each run (22.7 h recorded). The RQ1 error analysis,
replayed from the committed bundle, confirms the hypothesis: in the narrative style the
dependencies stated on the predecessor's side are the ones missed, 88.1 % [84.6, 91.3] of
gpt-oss-120b's missed edges against a base share of 47.7 %. The architect's answers 1–2 are
implemented: with `store_prompts = false` an invalid reply is cached only as its issue list, and
invariant 3 is reworded.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Housekeeping commit; quality gate and `-m "data or slow"` pass; task-6 tests exist and pass | `git show --stat f41d711`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (f41d711: `CLAUDE.md` invariant 3, `llm/core.py`, `client.py`, `cache.py`, ADR-0018, roadmap, 2 tests; ruff clean, 259 files formatted, mypy: no issues in 94 source files; `pytest -q`: 405 passed, 10 deselected in 70.0 s; `-m "data or slow"`: first run 23 passed, 1 failed (`test_reproduce_check_passes_on_the_repository`: `MANIFEST.json` recorded the absolute config path the test passes), fixed in 586af31, rerun 24 passed, 391 deselected in 480.1 s; task-6 tests: `tests/test_paper.py`, `tests/test_wbs_analysis.py`) |
| 2 | RQ1 error-analysis table generated; its main finding stated in the report | `uv run sentinel summarise-wbs results/wp6/20261023-215350-f5aad526` (at 238ac99, committed 8e0f9f3) | PASS (section "Error analysis: missed precedence edges" in the run's `summary.md` and `table_wp6_rq1_errors.tex`; results, rounds, bundle and manifest byte-identical; 640 of 640 round rows reproduced by the replay; finding under Numbers) |
| 3 | `paper/generated/` complete (EN + PL), deterministic, with MANIFEST; `reproduce --check` passes | `uv run sentinel paper` (at 2b48630); `uv run pytest -q -m slow tests/test_paper.py`; `uv run sentinel reproduce --check` | PASS (26 files: `numbers.tex`, `tab_rq1–5.tex`, six `fig_*.pdf` in English and Polish, `numbers.md`, `MANIFEST.json` with `git_dirty: false`; two generations byte-identical; check: 117 of 117 files identical, 40 s) |
| 4 | Limitations note; README section; report and roadmap; pushed; clean tree | `git push`; `git status --short` | PASS (`docs/notes/limitations.md`, README "Reproducing the results", this report, `docs/notes/WP7.md`, ADR-0020, roadmap `WP7: done`; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `src/sentinel/llm/core.py`: `withhold_invalid` (an answer that fails its schema keeps only its
  issue list, names outside the schema masked), `validate_reply` returns a withheld reply's
  stored error; `client.py`: a cache without prompts stores and returns invalid answers as
  withheld; `cache.py`: docstring. ADR-0018 amendment.
- `CLAUDE.md`: invariant 3 ("no LLM calls in the simulation engine or in rollouts; the agent may
  call the LLM at a deliberation, through the record/replay cache (spec §10)").
- `src/sentinel/wbs/narrate.py`: `EdgePhrasing`, `edge_phrasings` (texts unchanged);
  `score.py`: `match_activities`, `stated_edges` shared with the analysis; `analysis.py` (new):
  edge outcomes, cells, rates by side, number form and distance.
- `src/sentinel/experiments/wbs_errors.py` (new): replay of a run's sessions from its bundle,
  replay check, summary section, `table_wp6_rq1_errors.tex`, cluster-bootstrap intervals;
  `wbs_summary.py`: the section and table when the run has a bundle, `pinned`.
- `src/sentinel/experiments/runs.py`: `summary_provenance` (current or pinned commit and time);
  `forecast_summary.py`, `policy_summary.py`: `pinned` in `write_summaries` and `regenerate`.
- `src/sentinel/experiments/summary_tables.py` (new): summary tables by section, caption,
  columns, row key; `parse_cell`.
- `src/sentinel/experiments/paper.py` (new): config and run checks, 1,430 macros, tables EN/PL,
  level-3 ladder point, `numbers.md`, `MANIFEST.json`; `paper_figures.py` (new): six figures EN/PL.
- `src/sentinel/experiments/reproduce.py` (new): `--check`, `--commands`; `cli.py`: `paper`,
  `reproduce`.
- `rq5_common.py`: `read_rows`; `event_study.py`, `proposal_study.py`, `explanation_study.py`,
  `online_study.py`: `regenerate` from their CSVs.
- `configs/paper.toml` (new): the 14 runs with pinned SHA-256; `.pre-commit-config.yaml`:
  detect-secrets skips `paper/generated/MANIFEST.json`.
- Results: RQ1 summary regenerated (new section and table); the summaries of the five policy
  runs regenerated (`summary.md` commit line, WP4 policy line; `summary_manifest.json` inputs);
  `paper/generated/` (new, 1.5 MB).
- Tests: `test_llm.py` (+1, invalid replies withheld), `test_wbs_extract.py` (+1, a repair
  session without prompts replays), `test_wbs_narrate.py` (+1, phrasings read back from the
  text), `test_wbs_analysis.py` (new, 2, hand-made answer with known missing edges),
  `test_paper.py` (new, 9: macros parse and are defined once, number formatting, table widths EN
  and PL, refusals, summary cells, `--commands`; slow: determinism, `reproduce --check`).
- Docs: README "Reproducing the results", `docs/notes/limitations.md`, `docs/notes/WP7.md`,
  ADR-0020, roadmap, this report.

## Decisions
- **Numbers from summary cells** (ADR-0020). Every macro is a cell of a run's `summary.md`, as
  printed, found by section, caption, row key and column; its comment gives `file:line | table |
  row | column`, so each value can be checked against the summary (all 1,391 summary-sourced
  values occur on their cited line; `numbers.md` lists them with sources). The other 39 come from
  manifests (rows, hours, machine) and from one computed point (below).
- **Pinned hashes in `configs/paper.toml`.** Run manifests record no hashes of their data files,
  so the config pins the SHA-256 of each manifest and raw output (with detect-secrets pragmas);
  where a summary manifest records input hashes, they must match too.
- **Byte identity with pinned provenance.** `--check` regenerates in temporary copies with the
  commit and time recorded in the committed summary manifest or `MANIFEST.json`, so the
  comparison stays exact while the code moves on; runs without a summary manifest (WP1, WP2,
  RQ5) are deterministic already.
- **Regenerated summaries.** The policy runs had written `summary_manifest.json` without the
  manifest and config inputs that `regenerate` records, and the WP4 summaries had an older
  policy line; the five were regenerated once at d07a099 (tables and figures unchanged). The
  RQ1 summary gained its section at 238ac99.
- **RQ5 summaries from CSV.** Their runners summarise in memory; `regenerate` reads the CSVs back
  with a typed reader (empty → None, integers, floats, text) and reproduces the four committed
  summaries and tables byte for byte.
- **Withheld invalid replies.** With `store_prompts = false` the stored issue list keeps the error
  kind and message and per violation its type and location, with every name that is not a field,
  constant or enumerated value of the schema masked as `*` (pydantic messages and an extra
  field's name can echo the answer). The client returns the reply as stored, also when
  recording, so a replay makes the same requests; a repair round then sends an empty previous
  answer. Research runs (`store_prompts = true`) and all committed caches are unaffected.
- **Error analysis.** The edges of edge recall (both activities matched), pooled per backend,
  style and round; distance bins 0, 1–2, 3–5, 6+ paragraphs; number form = the stating block's
  duration; intervals by a cluster bootstrap over instances with its own seed key, so the RQ1
  summary's other numbers are unchanged.
- **Level 3 of the autonomy ladder** on the autonomy worlds (J30 every 8th, λ_A = 0.01) is not in
  any summary: it is aggregated from the main run's rows by `policy_summary.aggregate`, which
  reproduces the summary's pooled J30 Sentinel row exactly (37.1 [35.0, 39.3], 6.30, 40.3, 12.284).
- **Table widths** are estimated from STIX glyph advances + 10 % for Computer Modern, `\small`
  9 pt, `\tiny` 5 pt, `tabcolsep` 3 pt (no TeX on the server); a test keeps every table at most
  347 pt. RQ1 and RQ4 use group rows (backend and style, set) instead of columns.
- **Macro naming**: letters only, `RQone…RQfive` + metric + subject + set + λ_A or checkpoint,
  `Lo`/`Hi` for interval bounds (notes). Integers from 10,000 on get thousands separators
  (`75{,}486`, Polish `75\,486`); negative values a proper minus, `\ensuremath{-}`.
- ADRs created: ADR-0020 (paper-artifact pipeline); ADR-0018 amended (invalid replies).

## Deviations
- **"Data files' hashes differ from the manifest"**: the run manifests hold no such hashes, so
  they are pinned in `configs/paper.toml` and cross-checked with the summary manifests' inputs.
- **Six figures**: `fig_rq1.pdf` … `fig_rq5.pdf` plus `fig_rq4_autonomy.pdf`; the WP names
  `fig_rq2` … `fig_rq5` but describes an RQ1 figure and the autonomy ladder.
- **RQ1 figure with a legend**: three of four lines end at 100 % valid and two at recall 1, so
  direct labels collide; colours, markers and line styles still read in grey scale. The RQ4
  figure stacks its two sets (12.2 × 10 cm) so that direct labels have the full width.
- **Committed summaries regenerated beyond RQ1**: the five policy runs (see Decisions), which the
  constraint allows ("except regenerated summaries").
- **Scope of `--check`**: the 14 runs of `configs/paper.toml`; smoke runs and the superseded
  single-backend RQ1/RQ5 runs are evidence only and not checked.
- **Files beyond the WP's list**: `llm/core.py`, `client.py`, `cache.py`, `wbs/score.py`,
  `experiments/runs.py`, the four RQ5 study modules, `forecast_summary.py`, `policy_summary.py`,
  `cli.py`, `.pre-commit-config.yaml`; new helper modules `summary_tables.py`,
  `paper_figures.py`, `wbs_errors.py`.
- **Extra output `numbers.md`** (all macros with values and sources, for checking).
- **Polish table headers** shortened where the width required it ("Na czas [%]", "Δ [p.p.]").
- `reproduce --check` needs `data/psplib`: the RQ1 error analysis narrates the texts.

## Spec questions
1. **§10 cache records** do not yet say how an invalid reply is stored without prompts. Wording
   implemented: "With `store_prompts = false`, an answer that fails its schema is stored only as
   its issue list (error kind, and per violation its type and location, with names outside the
   schema masked); the client returns it as stored." `docs/spec/` not edited.
2. **Schema-valid answers with free text.** A string field can still carry a reason (e.g. a
   worker named "Ada K. (flu)"); the domain validator rejects the worker, but the valid reply is
   stored in full. Should answers with domain issues also be stored as issue lists for real
   data? That needs the domain validator inside the cache path.
3. **`docs/spec/architecture.md`** still names "client (Ollama/Groq)" and does not list
   `paper/generated/` or the `reproduce` command (WP6c question 3, not edited).

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2, CPython 3.12.15, uv 0.13.2, matplotlib 3.11.2; idle
machine (load 0.1–0.2), no Ollama run, no LLM call in the whole WP.

**Tests and checks.** Default `pytest -q`: 405 passed, 10 deselected in 69.9 s (393 at the end
of WP6c, 70.7 s); the 12 new default tests take under 1 s. `-m "data or slow"`: 24 passed in 480.1 s (438.3 s in WP6c; the two new slow tests take about 46 s).
`sentinel reproduce --check`: 117 of 117 files identical (91 summary files of the 14 runs and
the 26 files of `paper/generated/`) in 40 s. `sentinel paper`: 26 files, 1.5 MB, 3.6 s; two
generations byte-identical (slow test, 6.7 s). Replaying the 160 RQ1 sessions: 1.5 s.

**Table widths** (estimate, limit 347 pt = 12.2 cm):

| Table | English [pt] | Polish [pt] |
| --- | ---: | ---: |
| `tab_rq1.tex` | 279 | 306 |
| `tab_rq2.tex` | 290 | 297 |
| `tab_rq3.tex` | 288 | 326 |
| `tab_rq4.tex` | 332 | 334 |
| `tab_rq5.tex` | 314 | 334 |

**RQ1 error analysis** (run `results/wp6/20261023-215350-f5aad526`, section "Error analysis:
missed precedence edges" of its `summary.md`; edges: true edges whose two activities the answer
matches, pooled over 40 sessions; recall by side with 95 % cluster bootstrap intervals over
instances; round 3 is the final answer of repair):

| Backend | Style | Round | Edges | Recall | Successor side | Predecessor side | Missed | Missed on predecessor side [%] | All on predecessor side [%] |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ollama | structured | 0 | 2023 | 0.997 | 0.997 (2023) | - (0) | 6 | 0.0 | 0.0 |
| ollama | structured | 3 | 2023 | 0.997 | 0.997 (2023) | - (0) | 6 | 0.0 | 0.0 |
| ollama | narrative | 0 | 1506 | 0.516 | 0.902 [0.873, 0.931] | 0.117 [0.094, 0.142] | 729 | 89.7 [86.9, 92.6] | 49.2 |
| ollama | narrative | 3 | 1510 | 0.515 | 0.901 [0.870, 0.930] | 0.117 [0.093, 0.142] | 733 | 89.6 [86.8, 92.5] | 49.3 |
| openrouter | structured | 0 | 2070 | 1.000 | 1.000 (2070) | - (0) | 0 | - | 0.0 |
| openrouter | structured | 3 | 2070 | 1.000 | 1.000 (2070) | - (0) | 0 | - | 0.0 |
| openrouter | narrative | 0 | 1994 | 0.743 | 0.942 [0.922, 0.958] | 0.526 [0.487, 0.567] | 512 | 88.1 [84.6, 91.3] | 47.7 |
| openrouter | narrative | 3 | 2055 | 0.741 | 0.938 [0.917, 0.956] | 0.528 [0.490, 0.567] | 532 | 87.6 [83.9, 90.9] | 48.0 |

**Finding.** The hypothesis holds. In the narrative style, dependencies stated on the
predecessor's side ("A must be finished before C begins") are the ones missed: gpt-oss-120b
recalls 94 % of the successor-side edges but 53 % of the predecessor-side ones, so 88 % of its
missed edges are predecessor-side although only 48 % of all edges are; qwen2.5:7b recalls 90 %
against 12 %, and 90 % of its missed edges are predecessor-side. Repair does not help, since an
answer without an edge is still valid and the validator has nothing to report. Distance matters
only on the predecessor side (gpt-oss-120b: 0.69 in the same paragraph, 0.48–0.50 at three or
more paragraphs); the number form does not (0.750 in words, 0.737 in digits). The structured
style, which lists every predecessor with its successor, reaches recall 0.997 and 1.000. Since
the side of each dependency is drawn at random, the effect is causal for these texts.

**Autonomy ladder** (J30 every 8th, λ_A = 0.01, 240 runs each; macros `\RQfourAuto…`):

| Autonomy level | On time δ_D = 0.2 [%] | Nervousness | Seconds per run | Source |
| --- | ---: | ---: | ---: | --- |
| Λ = 0 | 22.5 [17.7, 28.2] | 9.6 | 86.279 | autonomy run summary |
| Λ = 1 | 23.3 [18.4, 29.1] | 27.4 | 78.735 | autonomy run summary |
| Λ = 2 | 29.6 [24.2, 35.6] | 45.1 | 26.725 | ablation run summary |
| Λ = 3 | 33.8 [28.1, 39.9] | 48.3 | 14.485 | main run rows, `policy_summary.aggregate` |
| NoReaction / FullResolve | 21.2 / 24.6 | 0.0 / 193.4 | – | autonomy run summary |

**Generated macros** (1,430; English values; `paper/generated/numbers.md` gives each source
cell, `paper/generated/numbers.tex` the definitions; the Polish file has the same names):

**RQ1** (226 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\RQoneValidQwenStructuredSingle` | 97.5 | `\RQoneValidQwenStructuredSingleLo` | 87.1 |
| `\RQoneValidQwenStructuredSingleHi` | 99.6 | `\RQoneExactQwenStructuredSingle` | 50.0 |
| `\RQoneExactQwenStructuredSingleLo` | 35.2 | `\RQoneExactQwenStructuredSingleHi` | 64.8 |
| `\RQoneActRecallQwenStructuredSingle` | 0.987 | `\RQoneEdgeRecallQwenStructuredSingle` | 0.996 |
| `\RQoneEdgeFoneQwenStructuredSingle` | 0.997 | `\RQoneValidQwenStructuredRepair` | 100.0 |
| `\RQoneValidQwenStructuredRepairLo` | 91.2 | `\RQoneValidQwenStructuredRepairHi` | 100.0 |
| `\RQoneExactQwenStructuredRepair` | 50.0 | `\RQoneExactQwenStructuredRepairLo` | 35.2 |
| `\RQoneExactQwenStructuredRepairHi` | 64.8 | `\RQoneActRecallQwenStructuredRepair` | 0.987 |
| `\RQoneEdgeRecallQwenStructuredRepair` | 0.996 | `\RQoneEdgeFoneQwenStructuredRepair` | 0.997 |
| `\RQoneDeltaValidQwenStructured` | +2.5 | `\RQoneDeltaValidQwenStructuredLo` | +0.0 |
| `\RQoneDeltaValidQwenStructuredHi` | +7.5 | `\RQoneDeltaExactQwenStructured` | +0.0 |
| `\RQoneDeltaExactQwenStructuredLo` | +0.0 | `\RQoneDeltaExactQwenStructuredHi` | +0.0 |
| `\RQoneDeltaEdgeFoneQwenStructured` | +0.000 | `\RQoneDeltaEdgeFoneQwenStructuredLo` | +0.000 |
| `\RQoneDeltaEdgeFoneQwenStructuredHi` | +0.001 | `\RQoneValidQwenNarrativeSingle` | 2.5 |
| `\RQoneValidQwenNarrativeSingleLo` | 0.4 | `\RQoneValidQwenNarrativeSingleHi` | 12.9 |
| `\RQoneExactQwenNarrativeSingle` | 0.0 | `\RQoneExactQwenNarrativeSingleLo` | 0.0 |
| `\RQoneExactQwenNarrativeSingleHi` | 8.8 | `\RQoneActRecallQwenNarrativeSingle` | 0.851 |
| `\RQoneEdgeRecallQwenNarrativeSingle` | 0.515 | `\RQoneEdgeFoneQwenNarrativeSingle` | 0.594 |
| `\RQoneValidQwenNarrativeRepair` | 2.5 | `\RQoneValidQwenNarrativeRepairLo` | 0.4 |
| `\RQoneValidQwenNarrativeRepairHi` | 12.9 | `\RQoneExactQwenNarrativeRepair` | 0.0 |
| `\RQoneExactQwenNarrativeRepairLo` | 0.0 | `\RQoneExactQwenNarrativeRepairHi` | 8.8 |
| `\RQoneActRecallQwenNarrativeRepair` | 0.852 | `\RQoneEdgeRecallQwenNarrativeRepair` | 0.514 |
| `\RQoneEdgeFoneQwenNarrativeRepair` | 0.592 | `\RQoneDeltaValidQwenNarrative` | +0.0 |
| `\RQoneDeltaValidQwenNarrativeLo` | +0.0 | `\RQoneDeltaValidQwenNarrativeHi` | +0.0 |
| `\RQoneDeltaExactQwenNarrative` | +0.0 | `\RQoneDeltaExactQwenNarrativeLo` | +0.0 |
| `\RQoneDeltaExactQwenNarrativeHi` | +0.0 | `\RQoneDeltaEdgeFoneQwenNarrative` | -0.002 |
| `\RQoneDeltaEdgeFoneQwenNarrativeLo` | -0.005 | `\RQoneDeltaEdgeFoneQwenNarrativeHi` | +0.001 |
| `\RQoneValidQwenPooledSingle` | 50.0 | `\RQoneValidQwenPooledSingleLo` | 39.3 |
| `\RQoneValidQwenPooledSingleHi` | 60.7 | `\RQoneExactQwenPooledSingle` | 25.0 |
| `\RQoneExactQwenPooledSingleLo` | 16.8 | `\RQoneExactQwenPooledSingleHi` | 35.5 |
| `\RQoneActRecallQwenPooledSingle` | 0.919 | `\RQoneEdgeRecallQwenPooledSingle` | 0.756 |
| `\RQoneEdgeFoneQwenPooledSingle` | 0.796 | `\RQoneValidQwenPooledRepair` | 51.2 |
| `\RQoneValidQwenPooledRepairLo` | 40.5 | `\RQoneValidQwenPooledRepairHi` | 61.9 |
| `\RQoneExactQwenPooledRepair` | 25.0 | `\RQoneExactQwenPooledRepairLo` | 16.8 |
| `\RQoneExactQwenPooledRepairHi` | 35.5 | `\RQoneActRecallQwenPooledRepair` | 0.919 |
| `\RQoneEdgeRecallQwenPooledRepair` | 0.755 | `\RQoneEdgeFoneQwenPooledRepair` | 0.795 |
| `\RQoneDeltaValidQwenPooled` | +1.2 | `\RQoneDeltaValidQwenPooledLo` | +0.0 |
| `\RQoneDeltaValidQwenPooledHi` | +3.8 | `\RQoneDeltaExactQwenPooled` | +0.0 |
| `\RQoneDeltaExactQwenPooledLo` | +0.0 | `\RQoneDeltaExactQwenPooledHi` | +0.0 |
| `\RQoneDeltaEdgeFoneQwenPooled` | -0.001 | `\RQoneDeltaEdgeFoneQwenPooledLo` | -0.003 |
| `\RQoneDeltaEdgeFoneQwenPooledHi` | +0.000 | `\RQoneValidGptOssStructuredSingle` | 100.0 |
| `\RQoneValidGptOssStructuredSingleLo` | 91.2 | `\RQoneValidGptOssStructuredSingleHi` | 100.0 |
| `\RQoneExactGptOssStructuredSingle` | 100.0 | `\RQoneExactGptOssStructuredSingleLo` | 91.2 |
| `\RQoneExactGptOssStructuredSingleHi` | 100.0 | `\RQoneActRecallGptOssStructuredSingle` | 1.000 |
| `\RQoneEdgeRecallGptOssStructuredSingle` | 1.000 | `\RQoneEdgeFoneGptOssStructuredSingle` | 1.000 |
| `\RQoneValidGptOssStructuredRepair` | 100.0 | `\RQoneValidGptOssStructuredRepairLo` | 91.2 |
| `\RQoneValidGptOssStructuredRepairHi` | 100.0 | `\RQoneExactGptOssStructuredRepair` | 100.0 |
| `\RQoneExactGptOssStructuredRepairLo` | 91.2 | `\RQoneExactGptOssStructuredRepairHi` | 100.0 |
| `\RQoneActRecallGptOssStructuredRepair` | 1.000 | `\RQoneEdgeRecallGptOssStructuredRepair` | 1.000 |
| `\RQoneEdgeFoneGptOssStructuredRepair` | 1.000 | `\RQoneDeltaValidGptOssStructured` | +0.0 |
| `\RQoneDeltaValidGptOssStructuredLo` | +0.0 | `\RQoneDeltaValidGptOssStructuredHi` | +0.0 |
| `\RQoneDeltaExactGptOssStructured` | +0.0 | `\RQoneDeltaExactGptOssStructuredLo` | +0.0 |
| `\RQoneDeltaExactGptOssStructuredHi` | +0.0 | `\RQoneDeltaEdgeFoneGptOssStructured` | +0.000 |
| `\RQoneDeltaEdgeFoneGptOssStructuredLo` | +0.000 | `\RQoneDeltaEdgeFoneGptOssStructuredHi` | +0.000 |
| `\RQoneValidGptOssNarrativeSingle` | 72.5 | `\RQoneValidGptOssNarrativeSingleLo` | 57.2 |
| `\RQoneValidGptOssNarrativeSingleHi` | 83.9 | `\RQoneExactGptOssNarrativeSingle` | 0.0 |
| `\RQoneExactGptOssNarrativeSingleLo` | 0.0 | `\RQoneExactGptOssNarrativeSingleHi` | 8.8 |
| `\RQoneActRecallGptOssNarrativeSingle` | 0.978 | `\RQoneEdgeRecallGptOssNarrativeSingle` | 0.747 |
| `\RQoneEdgeFoneGptOssNarrativeSingle` | 0.841 | `\RQoneValidGptOssNarrativeRepair` | 100.0 |
| `\RQoneValidGptOssNarrativeRepairLo` | 91.2 | `\RQoneValidGptOssNarrativeRepairHi` | 100.0 |
| `\RQoneExactGptOssNarrativeRepair` | 0.0 | `\RQoneExactGptOssNarrativeRepairLo` | 0.0 |
| `\RQoneExactGptOssNarrativeRepairHi` | 8.8 | `\RQoneActRecallGptOssNarrativeRepair` | 0.995 |
| `\RQoneEdgeRecallGptOssNarrativeRepair` | 0.745 | `\RQoneEdgeFoneGptOssNarrativeRepair` | 0.841 |
| `\RQoneDeltaValidGptOssNarrative` | +27.5 | `\RQoneDeltaValidGptOssNarrativeLo` | +15.0 |
| `\RQoneDeltaValidGptOssNarrativeHi` | +42.5 | `\RQoneDeltaExactGptOssNarrative` | +0.0 |
| `\RQoneDeltaExactGptOssNarrativeLo` | +0.0 | `\RQoneDeltaExactGptOssNarrativeHi` | +0.0 |
| `\RQoneDeltaEdgeFoneGptOssNarrative` | -0.000 | `\RQoneDeltaEdgeFoneGptOssNarrativeLo` | -0.004 |
| `\RQoneDeltaEdgeFoneGptOssNarrativeHi` | +0.002 | `\RQoneValidGptOssPooledSingle` | 86.2 |
| `\RQoneValidGptOssPooledSingleLo` | 77.0 | `\RQoneValidGptOssPooledSingleHi` | 92.1 |
| `\RQoneExactGptOssPooledSingle` | 50.0 | `\RQoneExactGptOssPooledSingleLo` | 39.3 |
| `\RQoneExactGptOssPooledSingleHi` | 60.7 | `\RQoneActRecallGptOssPooledSingle` | 0.989 |
| `\RQoneEdgeRecallGptOssPooledSingle` | 0.873 | `\RQoneEdgeFoneGptOssPooledSingle` | 0.920 |
| `\RQoneValidGptOssPooledRepair` | 100.0 | `\RQoneValidGptOssPooledRepairLo` | 95.4 |
| `\RQoneValidGptOssPooledRepairHi` | 100.0 | `\RQoneExactGptOssPooledRepair` | 50.0 |
| `\RQoneExactGptOssPooledRepairLo` | 39.3 | `\RQoneExactGptOssPooledRepairHi` | 60.7 |
| `\RQoneActRecallGptOssPooledRepair` | 0.998 | `\RQoneEdgeRecallGptOssPooledRepair` | 0.872 |
| `\RQoneEdgeFoneGptOssPooledRepair` | 0.920 | `\RQoneDeltaValidGptOssPooled` | +13.8 |
| `\RQoneDeltaValidGptOssPooledLo` | +7.5 | `\RQoneDeltaValidGptOssPooledHi` | +21.2 |
| `\RQoneDeltaExactGptOssPooled` | +0.0 | `\RQoneDeltaExactGptOssPooledLo` | +0.0 |
| `\RQoneDeltaExactGptOssPooledHi` | +0.0 | `\RQoneDeltaEdgeFoneGptOssPooled` | -0.000 |
| `\RQoneDeltaEdgeFoneGptOssPooledLo` | -0.002 | `\RQoneDeltaEdgeFoneGptOssPooledHi` | +0.001 |
| `\RQoneErrSuccessorQwenRoundZero` | 0.902 | `\RQoneErrSuccessorQwenRoundZeroLo` | 0.873 |
| `\RQoneErrSuccessorQwenRoundZeroHi` | 0.931 | `\RQoneErrPredecessorQwenRoundZero` | 0.117 |
| `\RQoneErrPredecessorQwenRoundZeroLo` | 0.094 | `\RQoneErrPredecessorQwenRoundZeroHi` | 0.142 |
| `\RQoneErrGapQwenRoundZero` | +0.785 | `\RQoneErrGapQwenRoundZeroLo` | +0.745 |
| `\RQoneErrGapQwenRoundZeroHi` | +0.822 | `\RQoneErrMissedPredecessorQwenRoundZero` | 89.7 |
| `\RQoneErrMissedPredecessorQwenRoundZeroLo` | 86.9 | `\RQoneErrMissedPredecessorQwenRoundZeroHi` | 92.6 |
| `\RQoneErrEdgesQwenRoundZero` | 1506 | `\RQoneErrRecallQwenRoundZero` | 0.516 |
| `\RQoneErrMissedQwenRoundZero` | 729 | `\RQoneErrPredecessorBaseQwenRoundZero` | 49.2 |
| `\RQoneErrSuccessorQwenRoundThree` | 0.901 | `\RQoneErrSuccessorQwenRoundThreeLo` | 0.870 |
| `\RQoneErrSuccessorQwenRoundThreeHi` | 0.930 | `\RQoneErrPredecessorQwenRoundThree` | 0.117 |
| `\RQoneErrPredecessorQwenRoundThreeLo` | 0.093 | `\RQoneErrPredecessorQwenRoundThreeHi` | 0.142 |
| `\RQoneErrGapQwenRoundThree` | +0.784 | `\RQoneErrGapQwenRoundThreeLo` | +0.743 |
| `\RQoneErrGapQwenRoundThreeHi` | +0.822 | `\RQoneErrMissedPredecessorQwenRoundThree` | 89.6 |
| `\RQoneErrMissedPredecessorQwenRoundThreeLo` | 86.8 | `\RQoneErrMissedPredecessorQwenRoundThreeHi` | 92.5 |
| `\RQoneErrEdgesQwenRoundThree` | 1510 | `\RQoneErrRecallQwenRoundThree` | 0.515 |
| `\RQoneErrMissedQwenRoundThree` | 733 | `\RQoneErrPredecessorBaseQwenRoundThree` | 49.3 |
| `\RQoneErrSuccessorGptOssRoundZero` | 0.942 | `\RQoneErrSuccessorGptOssRoundZeroLo` | 0.922 |
| `\RQoneErrSuccessorGptOssRoundZeroHi` | 0.958 | `\RQoneErrPredecessorGptOssRoundZero` | 0.526 |
| `\RQoneErrPredecessorGptOssRoundZeroLo` | 0.487 | `\RQoneErrPredecessorGptOssRoundZeroHi` | 0.567 |
| `\RQoneErrGapGptOssRoundZero` | +0.416 | `\RQoneErrGapGptOssRoundZeroLo` | +0.369 |
| `\RQoneErrGapGptOssRoundZeroHi` | +0.463 | `\RQoneErrMissedPredecessorGptOssRoundZero` | 88.1 |
| `\RQoneErrMissedPredecessorGptOssRoundZeroLo` | 84.6 | `\RQoneErrMissedPredecessorGptOssRoundZeroHi` | 91.3 |
| `\RQoneErrEdgesGptOssRoundZero` | 1994 | `\RQoneErrRecallGptOssRoundZero` | 0.743 |
| `\RQoneErrMissedGptOssRoundZero` | 512 | `\RQoneErrPredecessorBaseGptOssRoundZero` | 47.7 |
| `\RQoneErrSuccessorGptOssRoundThree` | 0.938 | `\RQoneErrSuccessorGptOssRoundThreeLo` | 0.917 |
| `\RQoneErrSuccessorGptOssRoundThreeHi` | 0.956 | `\RQoneErrPredecessorGptOssRoundThree` | 0.528 |
| `\RQoneErrPredecessorGptOssRoundThreeLo` | 0.490 | `\RQoneErrPredecessorGptOssRoundThreeHi` | 0.567 |
| `\RQoneErrGapGptOssRoundThree` | +0.410 | `\RQoneErrGapGptOssRoundThreeLo` | +0.365 |
| `\RQoneErrGapGptOssRoundThreeHi` | +0.455 | `\RQoneErrMissedPredecessorGptOssRoundThree` | 87.6 |
| `\RQoneErrMissedPredecessorGptOssRoundThreeLo` | 83.9 | `\RQoneErrMissedPredecessorGptOssRoundThreeHi` | 90.9 |
| `\RQoneErrEdgesGptOssRoundThree` | 2055 | `\RQoneErrRecallGptOssRoundThree` | 0.741 |
| `\RQoneErrMissedGptOssRoundThree` | 532 | `\RQoneErrPredecessorBaseGptOssRoundThree` | 48.0 |

**RQ2** (90 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\RQtwoInstancesJthirty` | 480 | `\RQtwoGapSgsLftJthirty` | 5.58 |
| `\RQtwoGapLbSgsLftJthirty` | 20.81 | `\RQtwoMatchesSgsLftJthirty` | 240 |
| `\RQtwoMatchesPctSgsLftJthirty` | 50.0 | `\RQtwoTimeSgsLftJthirty` | 0.0003 |
| `\RQtwoTimeMaxSgsLftJthirty` | 0.0043 | `\RQtwoGapSgsLstJthirty` | 4.92 |
| `\RQtwoGapLbSgsLstJthirty` | 19.95 | `\RQtwoMatchesSgsLstJthirty` | 246 |
| `\RQtwoMatchesPctSgsLstJthirty` | 51.2 | `\RQtwoTimeSgsLstJthirty` | 0.0003 |
| `\RQtwoTimeMaxSgsLstJthirty` | 0.0044 | `\RQtwoGapSgsMtsJthirty` | 6.56 |
| `\RQtwoGapLbSgsMtsJthirty` | 21.84 | `\RQtwoMatchesSgsMtsJthirty` | 213 |
| `\RQtwoMatchesPctSgsMtsJthirty` | 44.4 | `\RQtwoTimeSgsMtsJthirty` | 0.0002 |
| `\RQtwoTimeMaxSgsMtsJthirty` | 0.0043 | `\RQtwoGapSgsGrpwJthirty` | 10.31 |
| `\RQtwoGapLbSgsGrpwJthirty` | 26.26 | `\RQtwoMatchesSgsGrpwJthirty` | 182 |
| `\RQtwoMatchesPctSgsGrpwJthirty` | 37.9 | `\RQtwoTimeSgsGrpwJthirty` | 0.0003 |
| `\RQtwoTimeMaxSgsGrpwJthirty` | 0.0064 | `\RQtwoGapRbrsJthirty` | 0.82 |
| `\RQtwoGapLbRbrsJthirty` | 14.57 | `\RQtwoMatchesRbrsJthirty` | 370 |
| `\RQtwoMatchesPctRbrsJthirty` | 77.1 | `\RQtwoTimeRbrsJthirty` | 0.0865 |
| `\RQtwoTimeMaxRbrsJthirty` | 0.2423 | `\RQtwoGapCpsatOneJthirty` | 0.09 |
| `\RQtwoGapLbCpsatOneJthirty` | 13.53 | `\RQtwoMatchesCpsatOneJthirty` | 470 |
| `\RQtwoMatchesPctCpsatOneJthirty` | 97.9 | `\RQtwoTimeCpsatOneJthirty` | 0.0835 |
| `\RQtwoTimeMaxCpsatOneJthirty` | 1.0033 | `\RQtwoProvenCpsatOneJthirty` | 462 |
| `\RQtwoGapCpsatTenJthirty` | 0.01 | `\RQtwoGapLbCpsatTenJthirty` | 13.39 |
| `\RQtwoMatchesCpsatTenJthirty` | 477 | `\RQtwoMatchesPctCpsatTenJthirty` | 99.4 |
| `\RQtwoTimeCpsatTenJthirty` | 0.2968 | `\RQtwoTimeMaxCpsatTenJthirty` | 10.0480 |
| `\RQtwoProvenCpsatTenJthirty` | 474 | `\RQtwoInstancesJsixty` | 480 |
| `\RQtwoGapSgsLftJsixty` | 5.73 | `\RQtwoGapLbSgsLftJsixty` | 18.13 |
| `\RQtwoMatchesSgsLftJsixty` | 272 | `\RQtwoMatchesPctSgsLftJsixty` | 56.7 |
| `\RQtwoTimeSgsLftJsixty` | 0.0005 | `\RQtwoTimeMaxSgsLftJsixty` | 0.0053 |
| `\RQtwoGapSgsLstJsixty` | 5.20 | `\RQtwoGapLbSgsLstJsixty` | 17.45 |
| `\RQtwoMatchesSgsLstJsixty` | 281 | `\RQtwoMatchesPctSgsLstJsixty` | 58.5 |
| `\RQtwoTimeSgsLstJsixty` | 0.0005 | `\RQtwoTimeMaxSgsLstJsixty` | 0.0049 |
| `\RQtwoGapSgsMtsJsixty` | 6.66 | `\RQtwoGapLbSgsMtsJsixty` | 18.99 |
| `\RQtwoMatchesSgsMtsJsixty` | 232 | `\RQtwoMatchesPctSgsMtsJsixty` | 48.3 |
| `\RQtwoTimeSgsMtsJsixty` | 0.0004 | `\RQtwoTimeMaxSgsMtsJsixty` | 0.0034 |
| `\RQtwoGapSgsGrpwJsixty` | 12.80 | `\RQtwoGapLbSgsGrpwJsixty` | 26.02 |
| `\RQtwoMatchesSgsGrpwJsixty` | 159 | `\RQtwoMatchesPctSgsGrpwJsixty` | 33.1 |
| `\RQtwoTimeSgsGrpwJsixty` | 0.0005 | `\RQtwoTimeMaxSgsGrpwJsixty` | 0.0045 |
| `\RQtwoGapRbrsJsixty` | 2.56 | `\RQtwoGapLbRbrsJsixty` | 13.99 |
| `\RQtwoMatchesRbrsJsixty` | 328 | `\RQtwoMatchesPctRbrsJsixty` | 68.3 |
| `\RQtwoTimeRbrsJsixty` | 0.1390 | `\RQtwoTimeMaxRbrsJsixty` | 0.4967 |
| `\RQtwoGapCpsatOneJsixty` | 1.38 | `\RQtwoGapLbCpsatOneJsixty` | 12.51 |
| `\RQtwoMatchesCpsatOneJsixty` | 394 | `\RQtwoMatchesPctCpsatOneJsixty` | 82.1 |
| `\RQtwoTimeCpsatOneJsixty` | 0.2225 | `\RQtwoTimeMaxCpsatOneJsixty` | 1.0151 |
| `\RQtwoProvenCpsatOneJsixty` | 390 | `\RQtwoGapCpsatTenJsixty` | 0.85 |
| `\RQtwoGapLbCpsatTenJsixty` | 11.73 | `\RQtwoMatchesCpsatTenJsixty` | 417 |
| `\RQtwoMatchesPctCpsatTenJsixty` | 86.9 | `\RQtwoTimeCpsatTenJsixty` | 1.7440 |
| `\RQtwoTimeMaxCpsatTenJsixty` | 10.0754 | `\RQtwoProvenCpsatTenJsixty` | 405 |

**RQ3** (204 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\RQthreeOnTimeJthirtyFzero` | 0.299 | `\RQthreeUncJthirtyFzero` | 0.210 |
| `\RQthreeNJthirtyFzero` | 7680 | `\RQthreeBrierMcFullJthirtyFzero` | 0.174 |
| `\RQthreeBrierMcFullJthirtyFzeroLo` | 0.168 | `\RQthreeBrierMcFullJthirtyFzeroHi` | 0.181 |
| `\RQthreeBssMcFullJthirtyFzero` | 0.171 | `\RQthreeEceMcFullJthirtyFzero` | 0.015 |
| `\RQthreeAucMcFullJthirtyFzero` | 0.762 | `\RQthreePitCovMcFullJthirtyFzero` | 0.788 |
| `\RQthreeBrierMcNoFutureJthirtyFzero` | 0.653 | `\RQthreeBrierMcNoFutureJthirtyFzeroLo` | 0.634 |
| `\RQthreeBrierMcNoFutureJthirtyFzeroHi` | 0.669 | `\RQthreeBssMcNoFutureJthirtyFzero` | -2.112 |
| `\RQthreeEceMcNoFutureJthirtyFzero` | 0.665 | `\RQthreeAucMcNoFutureJthirtyFzero` | 0.589 |
| `\RQthreePitCovMcNoFutureJthirtyFzero` | 0.167 | `\RQthreeBrierDetJthirtyFzero` | 0.695 |
| `\RQthreeBrierDetJthirtyFzeroLo` | 0.675 | `\RQthreeBrierDetJthirtyFzeroHi` | 0.713 |
| `\RQthreeBssDetJthirtyFzero` | -2.313 | `\RQthreeEceDetJthirtyFzero` | 0.695 |
| `\RQthreeAucDetJthirtyFzero` | 0.504 | `\RQthreePitCovDetJthirtyFzero` | 0.001 |
| `\RQthreeDiffBrierDetJthirtyFzero` | -0.5209 | `\RQthreeDiffBrierDetJthirtyFzeroLo` | -0.5447 |
| `\RQthreeDiffBrierDetJthirtyFzeroHi` | -0.4954 | `\RQthreeDiffBrierMcNoFutureJthirtyFzero` | -0.4787 |
| `\RQthreeDiffBrierMcNoFutureJthirtyFzeroLo` | -0.5011 | `\RQthreeDiffBrierMcNoFutureJthirtyFzeroHi` | -0.4554 |
| `\RQthreeOnTimeJthirtyFfour` | 0.299 | `\RQthreeUncJthirtyFfour` | 0.210 |
| `\RQthreeNJthirtyFfour` | 7680 | `\RQthreeBrierMcFullJthirtyFfour` | 0.136 |
| `\RQthreeBrierMcFullJthirtyFfourLo` | 0.130 | `\RQthreeBrierMcFullJthirtyFfourHi` | 0.142 |
| `\RQthreeBssMcFullJthirtyFfour` | 0.351 | `\RQthreeEceMcFullJthirtyFfour` | 0.008 |
| `\RQthreeAucMcFullJthirtyFfour` | 0.865 | `\RQthreePitCovMcFullJthirtyFfour` | 0.798 |
| `\RQthreeBrierMcNoFutureJthirtyFfour` | 0.356 | `\RQthreeBrierMcNoFutureJthirtyFfourLo` | 0.340 |
| `\RQthreeBrierMcNoFutureJthirtyFfourHi` | 0.370 | `\RQthreeBssMcNoFutureJthirtyFfour` | -0.695 |
| `\RQthreeEceMcNoFutureJthirtyFfour` | 0.405 | `\RQthreeAucMcNoFutureJthirtyFfour` | 0.829 |
| `\RQthreePitCovMcNoFutureJthirtyFfour` | 0.284 | `\RQthreeBrierDetJthirtyFfour` | 0.559 |
| `\RQthreeBrierDetJthirtyFfourLo` | 0.541 | `\RQthreeBrierDetJthirtyFfourHi` | 0.578 |
| `\RQthreeBssDetJthirtyFfour` | -1.666 | `\RQthreeEceDetJthirtyFfour` | 0.559 |
| `\RQthreeAucDetJthirtyFfour` | 0.601 | `\RQthreePitCovDetJthirtyFfour` | 0.007 |
| `\RQthreeDiffBrierDetJthirtyFfour` | -0.4231 | `\RQthreeDiffBrierDetJthirtyFfourLo` | -0.4439 |
| `\RQthreeDiffBrierDetJthirtyFfourHi` | -0.4024 | `\RQthreeDiffBrierMcNoFutureJthirtyFfour` | -0.2193 |
| `\RQthreeDiffBrierMcNoFutureJthirtyFfourLo` | -0.2328 | `\RQthreeDiffBrierMcNoFutureJthirtyFfourHi` | -0.2039 |
| `\RQthreeOnTimeJthirtyFeight` | 0.299 | `\RQthreeUncJthirtyFeight` | 0.210 |
| `\RQthreeNJthirtyFeight` | 7680 | `\RQthreeBrierMcFullJthirtyFeight` | 0.096 |
| `\RQthreeBrierMcFullJthirtyFeightLo` | 0.091 | `\RQthreeBrierMcFullJthirtyFeightHi` | 0.102 |
| `\RQthreeBssMcFullJthirtyFeight` | 0.541 | `\RQthreeEceMcFullJthirtyFeight` | 0.009 |
| `\RQthreeAucMcFullJthirtyFeight` | 0.933 | `\RQthreePitCovMcFullJthirtyFeight` | 0.805 |
| `\RQthreeBrierMcNoFutureJthirtyFeight` | 0.155 | `\RQthreeBrierMcNoFutureJthirtyFeightLo` | 0.145 |
| `\RQthreeBrierMcNoFutureJthirtyFeightHi` | 0.166 | `\RQthreeBssMcNoFutureJthirtyFeight` | 0.261 |
| `\RQthreeEceMcNoFutureJthirtyFeight` | 0.173 | `\RQthreeAucMcNoFutureJthirtyFeight` | 0.926 |
| `\RQthreePitCovMcNoFutureJthirtyFeight` | 0.430 | `\RQthreeBrierDetJthirtyFeight` | 0.299 |
| `\RQthreeBrierDetJthirtyFeightLo` | 0.283 | `\RQthreeBrierDetJthirtyFeightHi` | 0.313 |
| `\RQthreeBssDetJthirtyFeight` | -0.425 | `\RQthreeEceDetJthirtyFeight` | 0.299 |
| `\RQthreeAucDetJthirtyFeight` | 0.784 | `\RQthreePitCovDetJthirtyFeight` | 0.035 |
| `\RQthreeDiffBrierDetJthirtyFeight` | -0.2026 | `\RQthreeDiffBrierDetJthirtyFeightLo` | -0.2157 |
| `\RQthreeDiffBrierDetJthirtyFeightHi` | -0.1881 | `\RQthreeDiffBrierMcNoFutureJthirtyFeight` | -0.0588 |
| `\RQthreeDiffBrierMcNoFutureJthirtyFeightLo` | -0.0657 | `\RQthreeDiffBrierMcNoFutureJthirtyFeightHi` | -0.0516 |
| `\RQthreeOnTimeJsixtyFzero` | 0.282 | `\RQthreeUncJsixtyFzero` | 0.202 |
| `\RQthreeNJsixtyFzero` | 7680 | `\RQthreeBrierMcFullJsixtyFzero` | 0.149 |
| `\RQthreeBrierMcFullJsixtyFzeroLo` | 0.141 | `\RQthreeBrierMcFullJsixtyFzeroHi` | 0.158 |
| `\RQthreeBssMcFullJsixtyFzero` | 0.264 | `\RQthreeEceMcFullJsixtyFzero` | 0.011 |
| `\RQthreeAucMcFullJsixtyFzero` | 0.826 | `\RQthreePitCovMcFullJsixtyFzero` | 0.804 |
| `\RQthreeBrierMcNoFutureJsixtyFzero` | 0.595 | `\RQthreeBrierMcNoFutureJsixtyFzeroLo` | 0.576 |
| `\RQthreeBrierMcNoFutureJsixtyFzeroHi` | 0.615 | `\RQthreeBssMcNoFutureJsixtyFzero` | -1.942 |
| `\RQthreeEceMcNoFutureJsixtyFzero` | 0.634 | `\RQthreeAucMcNoFutureJsixtyFzero` | 0.714 |
| `\RQthreePitCovMcNoFutureJsixtyFzero` | 0.139 | `\RQthreeBrierDetJsixtyFzero` | 0.716 |
| `\RQthreeBrierDetJsixtyFzeroLo` | 0.693 | `\RQthreeBrierDetJsixtyFzeroHi` | 0.737 |
| `\RQthreeBssDetJsixtyFzero` | -2.536 | `\RQthreeEceDetJsixtyFzero` | 0.716 |
| `\RQthreeAucDetJsixtyFzero` | 0.502 | `\RQthreePitCovDetJsixtyFzero` | 0.000 |
| `\RQthreeDiffBrierDetJsixtyFzero` | -0.5667 | `\RQthreeDiffBrierDetJsixtyFzeroLo` | -0.5947 |
| `\RQthreeDiffBrierDetJsixtyFzeroHi` | -0.5363 | `\RQthreeDiffBrierMcNoFutureJsixtyFzero` | -0.4464 |
| `\RQthreeDiffBrierMcNoFutureJsixtyFzeroLo` | -0.4704 | `\RQthreeDiffBrierMcNoFutureJsixtyFzeroHi` | -0.4226 |
| `\RQthreeOnTimeJsixtyFfour` | 0.282 | `\RQthreeUncJsixtyFfour` | 0.202 |
| `\RQthreeNJsixtyFfour` | 7680 | `\RQthreeBrierMcFullJsixtyFfour` | 0.120 |
| `\RQthreeBrierMcFullJsixtyFfourLo` | 0.113 | `\RQthreeBrierMcFullJsixtyFfourHi` | 0.128 |
| `\RQthreeBssMcFullJsixtyFfour` | 0.407 | `\RQthreeEceMcFullJsixtyFfour` | 0.012 |
| `\RQthreeAucMcFullJsixtyFfour` | 0.892 | `\RQthreePitCovMcFullJsixtyFfour` | 0.795 |
| `\RQthreeBrierMcNoFutureJsixtyFfour` | 0.312 | `\RQthreeBrierMcNoFutureJsixtyFfourLo` | 0.295 |
| `\RQthreeBrierMcNoFutureJsixtyFfourHi` | 0.328 | `\RQthreeBssMcNoFutureJsixtyFfour` | -0.542 |
| `\RQthreeEceMcNoFutureJsixtyFfour` | 0.359 | `\RQthreeAucMcNoFutureJsixtyFfour` | 0.862 |
| `\RQthreePitCovMcNoFutureJsixtyFfour` | 0.247 | `\RQthreeBrierDetJsixtyFfour` | 0.532 |
| `\RQthreeBrierDetJsixtyFfourLo` | 0.512 | `\RQthreeBrierDetJsixtyFfourHi` | 0.552 |
| `\RQthreeBssDetJsixtyFfour` | -1.627 | `\RQthreeEceDetJsixtyFfour` | 0.532 |
| `\RQthreeAucDetJsixtyFfour` | 0.629 | `\RQthreePitCovDetJsixtyFfour` | 0.005 |
| `\RQthreeDiffBrierDetJsixtyFfour` | -0.4115 | `\RQthreeDiffBrierDetJsixtyFfourLo` | -0.4331 |
| `\RQthreeDiffBrierDetJsixtyFfourHi` | -0.3906 | `\RQthreeDiffBrierMcNoFutureJsixtyFfour` | -0.1919 |
| `\RQthreeDiffBrierMcNoFutureJsixtyFfourLo` | -0.2059 | `\RQthreeDiffBrierMcNoFutureJsixtyFfourHi` | -0.1786 |
| `\RQthreeOnTimeJsixtyFeight` | 0.282 | `\RQthreeUncJsixtyFeight` | 0.202 |
| `\RQthreeNJsixtyFeight` | 7680 | `\RQthreeBrierMcFullJsixtyFeight` | 0.086 |
| `\RQthreeBrierMcFullJsixtyFeightLo` | 0.081 | `\RQthreeBrierMcFullJsixtyFeightHi` | 0.093 |
| `\RQthreeBssMcFullJsixtyFeight` | 0.573 | `\RQthreeEceMcFullJsixtyFeight` | 0.009 |
| `\RQthreeAucMcFullJsixtyFeight` | 0.944 | `\RQthreePitCovMcFullJsixtyFeight` | 0.794 |
| `\RQthreeBrierMcNoFutureJsixtyFeight` | 0.143 | `\RQthreeBrierMcNoFutureJsixtyFeightLo` | 0.134 |
| `\RQthreeBrierMcNoFutureJsixtyFeightHi` | 0.154 | `\RQthreeBssMcNoFutureJsixtyFeight` | 0.291 |
| `\RQthreeEceMcNoFutureJsixtyFeight` | 0.162 | `\RQthreeAucMcNoFutureJsixtyFeight` | 0.937 |
| `\RQthreePitCovMcNoFutureJsixtyFeight` | 0.371 | `\RQthreeBrierDetJsixtyFeight` | 0.288 |
| `\RQthreeBrierDetJsixtyFeightLo` | 0.273 | `\RQthreeBrierDetJsixtyFeightHi` | 0.304 |
| `\RQthreeBssDetJsixtyFeight` | -0.424 | `\RQthreeEceDetJsixtyFeight` | 0.288 |
| `\RQthreeAucDetJsixtyFeight` | 0.797 | `\RQthreePitCovDetJsixtyFeight` | 0.024 |
| `\RQthreeDiffBrierDetJsixtyFeight` | -0.2018 | `\RQthreeDiffBrierDetJsixtyFeightLo` | -0.2149 |
| `\RQthreeDiffBrierDetJsixtyFeightHi` | -0.1885 | `\RQthreeDiffBrierMcNoFutureJsixtyFeight` | -0.0570 |
| `\RQthreeDiffBrierMcNoFutureJsixtyFeightLo` | -0.0639 | `\RQthreeDiffBrierMcNoFutureJsixtyFeightHi` | -0.0504 |
| `\RQthreeMisspecBrierKappaHalfFzero` | 0.230 | `\RQthreeMisspecEceKappaHalfFzero` | 0.282 |
| `\RQthreeMisspecBrierKappaOneFzero` | 0.144 | `\RQthreeMisspecEceKappaOneFzero` | 0.031 |
| `\RQthreeMisspecBrierKappaTwoFzero` | 0.180 | `\RQthreeMisspecEceKappaTwoFzero` | 0.165 |
| `\RQthreeMisspecBrierPertWideFzero` | 0.158 | `\RQthreeMisspecEcePertWideFzero` | 0.109 |
| `\RQthreeMisspecBrierKappaHalfFfour` | 0.156 | `\RQthreeMisspecEceKappaHalfFfour` | 0.151 |
| `\RQthreeMisspecBrierKappaOneFfour` | 0.122 | `\RQthreeMisspecEceKappaOneFfour` | 0.034 |
| `\RQthreeMisspecBrierKappaTwoFfour` | 0.154 | `\RQthreeMisspecEceKappaTwoFfour` | 0.136 |
| `\RQthreeMisspecBrierPertWideFfour` | 0.137 | `\RQthreeMisspecEcePertWideFfour` | 0.092 |
| `\RQthreeMisspecBrierKappaHalfFeight` | 0.099 | `\RQthreeMisspecEceKappaHalfFeight` | 0.074 |
| `\RQthreeMisspecBrierKappaOneFeight` | 0.089 | `\RQthreeMisspecEceKappaOneFeight` | 0.042 |
| `\RQthreeMisspecBrierKappaTwoFeight` | 0.107 | `\RQthreeMisspecEceKappaTwoFeight` | 0.083 |
| `\RQthreeMisspecBrierPertWideFeight` | 0.098 | `\RQthreeMisspecEcePertWideFeight` | 0.063 |

**Scenario calibration** (60 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\CalibOnTimeDoneJthirtyLamZero` | 21.2 | `\CalibOnTimeDtwoJthirtyLamZero` | 51.2 |
| `\CalibOnTimeDtwoJthirtyLamZeroLo` | 50.2 | `\CalibOnTimeDtwoJthirtyLamZeroHi` | 52.2 |
| `\CalibOnTimeDthreeJthirtyLamZero` | 72.4 | `\CalibCRatioJthirtyLamZero` | 1.252 |
| `\CalibOnTimeDoneJthirtyLamHalf` | 8.9 | `\CalibOnTimeDtwoJthirtyLamHalf` | 33.3 |
| `\CalibOnTimeDtwoJthirtyLamHalfLo` | 32.3 | `\CalibOnTimeDtwoJthirtyLamHalfHi` | 34.2 |
| `\CalibOnTimeDthreeJthirtyLamHalf` | 58.6 | `\CalibCRatioJthirtyLamHalf` | 1.319 |
| `\CalibOnTimeDoneJthirtyLamOne` | 4.6 | `\CalibOnTimeDtwoJthirtyLamOne` | 22.9 |
| `\CalibOnTimeDtwoJthirtyLamOneLo` | 22.1 | `\CalibOnTimeDtwoJthirtyLamOneHi` | 23.8 |
| `\CalibOnTimeDthreeJthirtyLamOne` | 48.8 | `\CalibCRatioJthirtyLamOne` | 1.361 |
| `\CalibOnTimeDoneJthirtyLamTwo` | 1.5 | `\CalibOnTimeDtwoJthirtyLamTwo` | 12.8 |
| `\CalibOnTimeDtwoJthirtyLamTwoLo` | 12.1 | `\CalibOnTimeDtwoJthirtyLamTwoHi` | 13.5 |
| `\CalibOnTimeDthreeJthirtyLamTwo` | 35.6 | `\CalibCRatioJthirtyLamTwo` | 1.422 |
| `\CalibOnTimeDoneJthirtyDurationsOnly` | 66.5 | `\CalibOnTimeDtwoJthirtyDurationsOnly` | 97.2 |
| `\CalibOnTimeDtwoJthirtyDurationsOnlyLo` | 96.9 | `\CalibOnTimeDtwoJthirtyDurationsOnlyHi` | 97.5 |
| `\CalibOnTimeDthreeJthirtyDurationsOnly` | 99.9 | `\CalibCRatioJthirtyDurationsOnly` | 1.099 |
| `\CalibOnTimeDoneJsixtyLamZero` | 15.5 | `\CalibOnTimeDtwoJsixtyLamZero` | 46.5 |
| `\CalibOnTimeDtwoJsixtyLamZeroLo` | 45.5 | `\CalibOnTimeDtwoJsixtyLamZeroHi` | 47.5 |
| `\CalibOnTimeDthreeJsixtyLamZero` | 70.5 | `\CalibCRatioJsixtyLamZero` | 1.257 |
| `\CalibOnTimeDoneJsixtyLamHalf` | 5.4 | `\CalibOnTimeDtwoJsixtyLamHalf` | 30.0 |
| `\CalibOnTimeDtwoJsixtyLamHalfLo` | 29.1 | `\CalibOnTimeDtwoJsixtyLamHalfHi` | 30.9 |
| `\CalibOnTimeDthreeJsixtyLamHalf` | 56.3 | `\CalibCRatioJsixtyLamHalf` | 1.321 |
| `\CalibOnTimeDoneJsixtyLamOne` | 2.3 | `\CalibOnTimeDtwoJsixtyLamOne` | 21.0 |
| `\CalibOnTimeDtwoJsixtyLamOneLo` | 20.2 | `\CalibOnTimeDtwoJsixtyLamOneHi` | 21.8 |
| `\CalibOnTimeDthreeJsixtyLamOne` | 47.2 | `\CalibCRatioJsixtyLamOne` | 1.361 |
| `\CalibOnTimeDoneJsixtyLamTwo` | 0.7 | `\CalibOnTimeDtwoJsixtyLamTwo` | 11.3 |
| `\CalibOnTimeDtwoJsixtyLamTwoLo` | 10.7 | `\CalibOnTimeDtwoJsixtyLamTwoHi` | 12.0 |
| `\CalibOnTimeDthreeJsixtyLamTwo` | 35.6 | `\CalibCRatioJsixtyLamTwo` | 1.415 |
| `\CalibOnTimeDoneJsixtyDurationsOnly` | 53.1 | `\CalibOnTimeDtwoJsixtyDurationsOnly` | 92.3 |
| `\CalibOnTimeDtwoJsixtyDurationsOnlyLo` | 91.7 | `\CalibOnTimeDtwoJsixtyDurationsOnlyHi` | 92.8 |
| `\CalibOnTimeDthreeJsixtyDurationsOnly` | 99.5 | `\CalibCRatioJsixtyDurationsOnly` | 1.117 |

**RQ4** (606 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\RQfourOnTimeNoReactionJthirty` | 27.0 | `\RQfourOnTimeNoReactionJthirtyLo` | 25.0 |
| `\RQfourOnTimeNoReactionJthirtyHi` | 29.0 | `\RQfourOnTimeDthreeNoReactionJthirty` | 49.6 |
| `\RQfourOnTimeDthreeNoReactionJthirtyLo` | 47.3 | `\RQfourOnTimeDthreeNoReactionJthirtyHi` | 51.8 |
| `\RQfourCRatioNoReactionJthirty` | 1.356 | `\RQfourDeviationNoReactionJthirty` | 6.76 |
| `\RQfourNervousnessNoReactionJthirty` | 0.0 | `\RQfourCostBNoReactionJthirty` | 1.027 |
| `\RQfourSecondsPerRunNoReactionJthirty` | 0.005 | `\RQfourOnTimeNoReactionJthirtyLamZero` | 45.8 |
| `\RQfourOnTimeNoReactionJthirtyLamHalf` | 29.4 | `\RQfourOnTimeNoReactionJthirtyLamOne` | 20.6 |
| `\RQfourOnTimeNoReactionJthirtyLamTwo` | 12.1 | `\RQfourOnTimeAlwaysSubstJthirty` | 26.6 |
| `\RQfourOnTimeAlwaysSubstJthirtyLo` | 24.6 | `\RQfourOnTimeAlwaysSubstJthirtyHi` | 28.6 |
| `\RQfourOnTimeDthreeAlwaysSubstJthirty` | 48.2 | `\RQfourOnTimeDthreeAlwaysSubstJthirtyLo` | 46.0 |
| `\RQfourOnTimeDthreeAlwaysSubstJthirtyHi` | 50.5 | `\RQfourCRatioAlwaysSubstJthirty` | 1.364 |
| `\RQfourDeviationAlwaysSubstJthirty` | 6.98 | `\RQfourNervousnessAlwaysSubstJthirty` | 0.0 |
| `\RQfourCostBAlwaysSubstJthirty` | 1.044 | `\RQfourSecondsPerRunAlwaysSubstJthirty` | 0.009 |
| `\RQfourOnTimeAlwaysSubstJthirtyLamZero` | 45.8 | `\RQfourOnTimeAlwaysSubstJthirtyLamHalf` | 28.5 |
| `\RQfourOnTimeAlwaysSubstJthirtyLamOne` | 19.6 | `\RQfourOnTimeAlwaysSubstJthirtyLamTwo` | 12.3 |
| `\RQfourVsNoReactionOnTimeAlwaysSubstJthirty` | -0.4 | `\RQfourVsNoReactionOnTimeAlwaysSubstJthirtyLo` | -1.2 |
| `\RQfourVsNoReactionOnTimeAlwaysSubstJthirtyHi` | 0.3 | `\RQfourVsNoReactionCRatioAlwaysSubstJthirty` | +0.008 |
| `\RQfourVsNoReactionCRatioAlwaysSubstJthirtyLo` | 0.005 | `\RQfourVsNoReactionCRatioAlwaysSubstJthirtyHi` | 0.011 |
| `\RQfourVsNoReactionDeviationAlwaysSubstJthirty` | +0.22 | `\RQfourVsNoReactionDeviationAlwaysSubstJthirtyLo` | 0.16 |
| `\RQfourVsNoReactionDeviationAlwaysSubstJthirtyHi` | 0.27 | `\RQfourOnTimeFullResolveJthirty` | 31.3 |
| `\RQfourOnTimeFullResolveJthirtyLo` | 29.3 | `\RQfourOnTimeFullResolveJthirtyHi` | 33.4 |
| `\RQfourOnTimeDthreeFullResolveJthirty` | 56.3 | `\RQfourOnTimeDthreeFullResolveJthirtyLo` | 54.1 |
| `\RQfourOnTimeDthreeFullResolveJthirtyHi` | 58.5 | `\RQfourCRatioFullResolveJthirty` | 1.320 |
| `\RQfourDeviationFullResolveJthirty` | 7.11 | `\RQfourNervousnessFullResolveJthirty` | 151.6 |
| `\RQfourCostBFullResolveJthirty` | 1.025 | `\RQfourSecondsPerRunFullResolveJthirty` | 0.749 |
| `\RQfourOnTimeFullResolveJthirtyLamZero` | 52.1 | `\RQfourOnTimeFullResolveJthirtyLamHalf` | 33.8 |
| `\RQfourOnTimeFullResolveJthirtyLamOne` | 25.2 | `\RQfourOnTimeFullResolveJthirtyLamTwo` | 14.2 |
| `\RQfourVsNoReactionOnTimeFullResolveJthirty` | +4.3 | `\RQfourVsNoReactionOnTimeFullResolveJthirtyLo` | 2.7 |
| `\RQfourVsNoReactionOnTimeFullResolveJthirtyHi` | 5.8 | `\RQfourVsNoReactionCRatioFullResolveJthirty` | -0.036 |
| `\RQfourVsNoReactionCRatioFullResolveJthirtyLo` | -0.043 | `\RQfourVsNoReactionCRatioFullResolveJthirtyHi` | -0.029 |
| `\RQfourVsNoReactionDeviationFullResolveJthirty` | +0.35 | `\RQfourVsNoReactionDeviationFullResolveJthirtyLo` | 0.21 |
| `\RQfourVsNoReactionDeviationFullResolveJthirtyHi` | 0.51 | `\RQfourOnTimeFullResolveSubstJthirty` | 30.9 |
| `\RQfourOnTimeFullResolveSubstJthirtyLo` | 28.9 | `\RQfourOnTimeFullResolveSubstJthirtyHi` | 33.0 |
| `\RQfourOnTimeDthreeFullResolveSubstJthirty` | 54.8 | `\RQfourOnTimeDthreeFullResolveSubstJthirtyLo` | 52.6 |
| `\RQfourOnTimeDthreeFullResolveSubstJthirtyHi` | 57.1 | `\RQfourCRatioFullResolveSubstJthirty` | 1.326 |
| `\RQfourDeviationFullResolveSubstJthirty` | 7.31 | `\RQfourNervousnessFullResolveSubstJthirty` | 156.3 |
| `\RQfourCostBFullResolveSubstJthirty` | 1.041 | `\RQfourSecondsPerRunFullResolveSubstJthirty` | 0.778 |
| `\RQfourOnTimeFullResolveSubstJthirtyLamZero` | 52.1 | `\RQfourOnTimeFullResolveSubstJthirtyLamHalf` | 33.3 |
| `\RQfourOnTimeFullResolveSubstJthirtyLamOne` | 24.6 | `\RQfourOnTimeFullResolveSubstJthirtyLamTwo` | 13.5 |
| `\RQfourVsNoReactionOnTimeFullResolveSubstJthirty` | +3.9 | `\RQfourVsNoReactionOnTimeFullResolveSubstJthirtyLo` | 2.2 |
| `\RQfourVsNoReactionOnTimeFullResolveSubstJthirtyHi` | 5.5 | `\RQfourVsNoReactionCRatioFullResolveSubstJthirty` | -0.030 |
| `\RQfourVsNoReactionCRatioFullResolveSubstJthirtyLo` | -0.036 | `\RQfourVsNoReactionCRatioFullResolveSubstJthirtyHi` | -0.022 |
| `\RQfourVsNoReactionDeviationFullResolveSubstJthirty` | +0.54 | `\RQfourVsNoReactionDeviationFullResolveSubstJthirtyLo` | 0.38 |
| `\RQfourVsNoReactionDeviationFullResolveSubstJthirtyHi` | 0.73 | `\RQfourOnTimeStableResolveSubstJthirty` | 30.5 |
| `\RQfourOnTimeStableResolveSubstJthirtyLo` | 28.5 | `\RQfourOnTimeStableResolveSubstJthirtyHi` | 32.6 |
| `\RQfourOnTimeDthreeStableResolveSubstJthirty` | 55.2 | `\RQfourOnTimeDthreeStableResolveSubstJthirtyLo` | 52.9 |
| `\RQfourOnTimeDthreeStableResolveSubstJthirtyHi` | 57.4 | `\RQfourCRatioStableResolveSubstJthirty` | 1.329 |
| `\RQfourDeviationStableResolveSubstJthirty` | 7.00 | `\RQfourNervousnessStableResolveSubstJthirty` | 135.8 |
| `\RQfourCostBStableResolveSubstJthirty` | 1.042 | `\RQfourSecondsPerRunStableResolveSubstJthirty` | 1.331 |
| `\RQfourOnTimeStableResolveSubstJthirtyLamZero` | 51.2 | `\RQfourOnTimeStableResolveSubstJthirtyLamHalf` | 33.5 |
| `\RQfourOnTimeStableResolveSubstJthirtyLamOne` | 24.2 | `\RQfourOnTimeStableResolveSubstJthirtyLamTwo` | 13.1 |
| `\RQfourVsNoReactionOnTimeStableResolveSubstJthirty` | +3.5 | `\RQfourVsNoReactionOnTimeStableResolveSubstJthirtyLo` | 2.0 |
| `\RQfourVsNoReactionOnTimeStableResolveSubstJthirtyHi` | 5.0 | `\RQfourVsNoReactionCRatioStableResolveSubstJthirty` | -0.027 |
| `\RQfourVsNoReactionCRatioStableResolveSubstJthirtyLo` | -0.035 | `\RQfourVsNoReactionCRatioStableResolveSubstJthirtyHi` | -0.017 |
| `\RQfourVsNoReactionDeviationStableResolveSubstJthirty` | +0.24 | `\RQfourVsNoReactionDeviationStableResolveSubstJthirtyLo` | 0.09 |
| `\RQfourVsNoReactionDeviationStableResolveSubstJthirtyHi` | 0.39 | `\RQfourOnTimeSentinelJthirty` | 37.1 |
| `\RQfourOnTimeSentinelJthirtyLo` | 35.0 | `\RQfourOnTimeSentinelJthirtyHi` | 39.3 |
| `\RQfourOnTimeDthreeSentinelJthirty` | 64.2 | `\RQfourOnTimeDthreeSentinelJthirtyLo` | 62.0 |
| `\RQfourOnTimeDthreeSentinelJthirtyHi` | 66.3 | `\RQfourCRatioSentinelJthirty` | 1.292 |
| `\RQfourDeviationSentinelJthirty` | 6.30 | `\RQfourNervousnessSentinelJthirty` | 40.3 |
| `\RQfourCostBSentinelJthirty` | 1.037 | `\RQfourSecondsPerRunSentinelJthirty` | 12.284 |
| `\RQfourOnTimeSentinelJthirtyLamZero` | 57.7 | `\RQfourOnTimeSentinelJthirtyLamHalf` | 39.8 |
| `\RQfourOnTimeSentinelJthirtyLamOne` | 32.1 | `\RQfourOnTimeSentinelJthirtyLamTwo` | 19.0 |
| `\RQfourVsNoReactionOnTimeSentinelJthirty` | +10.2 | `\RQfourVsNoReactionOnTimeSentinelJthirtyLo` | 8.1 |
| `\RQfourVsNoReactionOnTimeSentinelJthirtyHi` | 12.1 | `\RQfourVsNoReactionCRatioSentinelJthirty` | -0.063 |
| `\RQfourVsNoReactionCRatioSentinelJthirtyLo` | -0.072 | `\RQfourVsNoReactionCRatioSentinelJthirtyHi` | -0.055 |
| `\RQfourVsNoReactionDeviationSentinelJthirty` | -0.46 | `\RQfourVsNoReactionDeviationSentinelJthirtyLo` | -0.58 |
| `\RQfourVsNoReactionDeviationSentinelJthirtyHi` | -0.34 | `\RQfourVsNoReactionOnTimeDthreeSentinelJthirty` | +14.6 |
| `\RQfourVsNoReactionOnTimeDthreeSentinelJthirtyLo` | 12.2 | `\RQfourVsNoReactionOnTimeDthreeSentinelJthirtyHi` | 17.1 |
| `\RQfourVsFullResolveOnTimeSentinelJthirty` | +5.8 | `\RQfourVsFullResolveOnTimeSentinelJthirtyLo` | 4.3 |
| `\RQfourVsFullResolveOnTimeSentinelJthirtyHi` | 7.5 | `\RQfourVsFullResolveOnTimeDthreeSentinelJthirty` | +7.9 |
| `\RQfourVsFullResolveOnTimeDthreeSentinelJthirtyLo` | 6.1 | `\RQfourVsFullResolveOnTimeDthreeSentinelJthirtyHi` | 9.9 |
| `\RQfourVsFullResolveCRatioSentinelJthirty` | -0.027 | `\RQfourVsFullResolveCRatioSentinelJthirtyLo` | -0.032 |
| `\RQfourVsFullResolveCRatioSentinelJthirtyHi` | -0.023 | `\RQfourVsFullResolveDeviationSentinelJthirty` | -0.81 |
| `\RQfourVsFullResolveDeviationSentinelJthirtyLo` | -0.96 | `\RQfourVsFullResolveDeviationSentinelJthirtyHi` | -0.67 |
| `\RQfourOvertimeShareSentinelJthirty` | 0.0171 | `\RQfourHiredSentinelJthirty` | 2.88 |
| `\RQfourDeliberationsSentinelJthirty` | 35.5 | `\RQfourGateExitsSentinelJthirty` | 1.7 |
| `\RQfourRolloutsPerDeliberationSentinelJthirty` | 432 | `\RQfourSecondsPerDeliberationSentinelJthirty` | 0.343 |
| `\RQfourNeedsMetSentinelJthirty` | 4.8 | `\RQfourChoseNoopSentinelJthirty` | 85.5 |
| `\RQfourChoseOvertimeSentinelJthirty` | 2.6 | `\RQfourChoseReseqSentinelJthirty` | 3.9 |
| `\RQfourOnTimeSentinelNoOTJthirty` | 32.3 | `\RQfourOnTimeSentinelNoOTJthirtyLo` | 30.3 |
| `\RQfourOnTimeSentinelNoOTJthirtyHi` | 34.5 | `\RQfourOnTimeDthreeSentinelNoOTJthirty` | 58.9 |
| `\RQfourOnTimeDthreeSentinelNoOTJthirtyLo` | 56.7 | `\RQfourOnTimeDthreeSentinelNoOTJthirtyHi` | 61.1 |
| `\RQfourCRatioSentinelNoOTJthirty` | 1.312 | `\RQfourDeviationSentinelNoOTJthirty` | 6.63 |
| `\RQfourNervousnessSentinelNoOTJthirty` | 34.3 | `\RQfourCostBSentinelNoOTJthirty` | 1.025 |
| `\RQfourSecondsPerRunSentinelNoOTJthirty` | 11.717 | `\RQfourOnTimeSentinelNoOTJthirtyLamZero` | 54.4 |
| `\RQfourOnTimeSentinelNoOTJthirtyLamHalf` | 34.0 | `\RQfourOnTimeSentinelNoOTJthirtyLamOne` | 26.2 |
| `\RQfourOnTimeSentinelNoOTJthirtyLamTwo` | 14.8 | `\RQfourVsNoReactionOnTimeSentinelNoOTJthirty` | +5.4 |
| `\RQfourVsNoReactionOnTimeSentinelNoOTJthirtyLo` | 3.8 | `\RQfourVsNoReactionOnTimeSentinelNoOTJthirtyHi` | 6.8 |
| `\RQfourVsNoReactionCRatioSentinelNoOTJthirty` | -0.043 | `\RQfourVsNoReactionCRatioSentinelNoOTJthirtyLo` | -0.050 |
| `\RQfourVsNoReactionCRatioSentinelNoOTJthirtyHi` | -0.037 | `\RQfourVsNoReactionDeviationSentinelNoOTJthirty` | -0.13 |
| `\RQfourVsNoReactionDeviationSentinelNoOTJthirtyLo` | -0.24 | `\RQfourVsNoReactionDeviationSentinelNoOTJthirtyHi` | -0.03 |
| `\RQfourVsNoReactionOnTimeDthreeSentinelNoOTJthirty` | +9.3 | `\RQfourVsNoReactionOnTimeDthreeSentinelNoOTJthirtyLo` | 7.5 |
| `\RQfourVsNoReactionOnTimeDthreeSentinelNoOTJthirtyHi` | 11.1 | `\RQfourVsFullResolveOnTimeSentinelNoOTJthirty` | +1.0 |
| `\RQfourVsFullResolveOnTimeSentinelNoOTJthirtyLo` | -0.1 | `\RQfourVsFullResolveOnTimeSentinelNoOTJthirtyHi` | 2.2 |
| `\RQfourVsFullResolveOnTimeDthreeSentinelNoOTJthirty` | +2.6 | `\RQfourVsFullResolveOnTimeDthreeSentinelNoOTJthirtyLo` | 1.3 |
| `\RQfourVsFullResolveOnTimeDthreeSentinelNoOTJthirtyHi` | 3.9 | `\RQfourVsFullResolveCRatioSentinelNoOTJthirty` | -0.007 |
| `\RQfourVsFullResolveCRatioSentinelNoOTJthirtyLo` | -0.011 | `\RQfourVsFullResolveCRatioSentinelNoOTJthirtyHi` | -0.004 |
| `\RQfourVsFullResolveDeviationSentinelNoOTJthirty` | -0.48 | `\RQfourVsFullResolveDeviationSentinelNoOTJthirtyLo` | -0.60 |
| `\RQfourVsFullResolveDeviationSentinelNoOTJthirtyHi` | -0.36 | `\RQfourOvertimeShareSentinelNoOTJthirty` | 0.0000 |
| `\RQfourHiredSentinelNoOTJthirty` | 0.00 | `\RQfourDeliberationsSentinelNoOTJthirty` | 35.9 |
| `\RQfourGateExitsSentinelNoOTJthirty` | 1.6 | `\RQfourRolloutsPerDeliberationSentinelNoOTJthirty` | 393 |
| `\RQfourSecondsPerDeliberationSentinelNoOTJthirty` | 0.323 | `\RQfourNeedsMetSentinelNoOTJthirty` | 4.5 |
| `\RQfourChoseNoopSentinelNoOTJthirty` | 88.2 | `\RQfourChoseOvertimeSentinelNoOTJthirty` | 0.0 |
| `\RQfourChoseReseqSentinelNoOTJthirty` | 4.1 | `\RQfourOnTimeNoReactionJsixty` | 23.8 |
| `\RQfourOnTimeNoReactionJsixtyLo` | 21.2 | `\RQfourOnTimeNoReactionJsixtyHi` | 26.5 |
| `\RQfourOnTimeDthreeNoReactionJsixty` | 46.4 | `\RQfourOnTimeDthreeNoReactionJsixtyLo` | 43.2 |
| `\RQfourOnTimeDthreeNoReactionJsixtyHi` | 49.5 | `\RQfourCRatioNoReactionJsixty` | 1.367 |
| `\RQfourDeviationNoReactionJsixty` | 9.43 | `\RQfourNervousnessNoReactionJsixty` | 0.0 |
| `\RQfourCostBNoReactionJsixty` | 1.013 | `\RQfourSecondsPerRunNoReactionJsixty` | 0.008 |
| `\RQfourOnTimeNoReactionJsixtyLamZero` | 42.1 | `\RQfourOnTimeNoReactionJsixtyLamHalf` | 25.8 |
| `\RQfourOnTimeNoReactionJsixtyLamOne` | 17.9 | `\RQfourOnTimeNoReactionJsixtyLamTwo` | 9.2 |
| `\RQfourOnTimeAlwaysSubstJsixty` | 23.3 | `\RQfourOnTimeAlwaysSubstJsixtyLo` | 20.8 |
| `\RQfourOnTimeAlwaysSubstJsixtyHi` | 26.1 | `\RQfourOnTimeDthreeAlwaysSubstJsixty` | 45.6 |
| `\RQfourOnTimeDthreeAlwaysSubstJsixtyLo` | 42.5 | `\RQfourOnTimeDthreeAlwaysSubstJsixtyHi` | 48.8 |
| `\RQfourCRatioAlwaysSubstJsixty` | 1.372 | `\RQfourDeviationAlwaysSubstJsixty` | 9.65 |
| `\RQfourNervousnessAlwaysSubstJsixty` | 0.0 | `\RQfourCostBAlwaysSubstJsixty` | 1.030 |
| `\RQfourSecondsPerRunAlwaysSubstJsixty` | 0.019 | `\RQfourOnTimeAlwaysSubstJsixtyLamZero` | 42.1 |
| `\RQfourOnTimeAlwaysSubstJsixtyLamHalf` | 25.4 | `\RQfourOnTimeAlwaysSubstJsixtyLamOne` | 19.2 |
| `\RQfourOnTimeAlwaysSubstJsixtyLamTwo` | 6.7 | `\RQfourVsNoReactionOnTimeAlwaysSubstJsixty` | -0.4 |
| `\RQfourVsNoReactionOnTimeAlwaysSubstJsixtyLo` | -1.5 | `\RQfourVsNoReactionOnTimeAlwaysSubstJsixtyHi` | 0.6 |
| `\RQfourVsNoReactionCRatioAlwaysSubstJsixty` | +0.006 | `\RQfourVsNoReactionCRatioAlwaysSubstJsixtyLo` | 0.002 |
| `\RQfourVsNoReactionCRatioAlwaysSubstJsixtyHi` | 0.010 | `\RQfourVsNoReactionDeviationAlwaysSubstJsixty` | +0.22 |
| `\RQfourVsNoReactionDeviationAlwaysSubstJsixtyLo` | 0.09 | `\RQfourVsNoReactionDeviationAlwaysSubstJsixtyHi` | 0.35 |
| `\RQfourOnTimeFullResolveJsixty` | 29.0 | `\RQfourOnTimeFullResolveJsixtyLo` | 26.2 |
| `\RQfourOnTimeFullResolveJsixtyHi` | 31.9 | `\RQfourOnTimeDthreeFullResolveJsixty` | 55.2 |
| `\RQfourOnTimeDthreeFullResolveJsixtyLo` | 52.0 | `\RQfourOnTimeDthreeFullResolveJsixtyHi` | 58.3 |
| `\RQfourCRatioFullResolveJsixty` | 1.319 | `\RQfourDeviationFullResolveJsixty` | 10.74 |
| `\RQfourNervousnessFullResolveJsixty` | 590.7 | `\RQfourCostBFullResolveJsixty` | 1.011 |
| `\RQfourSecondsPerRunFullResolveJsixty` | 6.347 | `\RQfourOnTimeFullResolveJsixtyLamZero` | 45.4 |
| `\RQfourOnTimeFullResolveJsixtyLamHalf` | 31.7 | `\RQfourOnTimeFullResolveJsixtyLamOne` | 23.8 |
| `\RQfourOnTimeFullResolveJsixtyLamTwo` | 15.0 | `\RQfourVsNoReactionOnTimeFullResolveJsixty` | +5.2 |
| `\RQfourVsNoReactionOnTimeFullResolveJsixtyLo` | 2.2 | `\RQfourVsNoReactionOnTimeFullResolveJsixtyHi` | 8.1 |
| `\RQfourVsNoReactionCRatioFullResolveJsixty` | -0.047 | `\RQfourVsNoReactionCRatioFullResolveJsixtyLo` | -0.058 |
| `\RQfourVsNoReactionCRatioFullResolveJsixtyHi` | -0.037 | `\RQfourVsNoReactionDeviationFullResolveJsixty` | +1.31 |
| `\RQfourVsNoReactionDeviationFullResolveJsixtyLo` | 0.86 | `\RQfourVsNoReactionDeviationFullResolveJsixtyHi` | 1.80 |
| `\RQfourOnTimeFullResolveSubstJsixty` | 28.7 | `\RQfourOnTimeFullResolveSubstJsixtyLo` | 26.0 |
| `\RQfourOnTimeFullResolveSubstJsixtyHi` | 31.7 | `\RQfourOnTimeDthreeFullResolveSubstJsixty` | 53.4 |
| `\RQfourOnTimeDthreeFullResolveSubstJsixtyLo` | 50.3 | `\RQfourOnTimeDthreeFullResolveSubstJsixtyHi` | 56.6 |
| `\RQfourCRatioFullResolveSubstJsixty` | 1.328 | `\RQfourDeviationFullResolveSubstJsixty` | 11.06 |
| `\RQfourNervousnessFullResolveSubstJsixty` | 619.5 | `\RQfourCostBFullResolveSubstJsixty` | 1.028 |
| `\RQfourSecondsPerRunFullResolveSubstJsixty` | 6.663 | `\RQfourOnTimeFullResolveSubstJsixtyLamZero` | 45.4 |
| `\RQfourOnTimeFullResolveSubstJsixtyLamHalf` | 31.2 | `\RQfourOnTimeFullResolveSubstJsixtyLamOne` | 23.3 |
| `\RQfourOnTimeFullResolveSubstJsixtyLamTwo` | 15.0 | `\RQfourVsNoReactionOnTimeFullResolveSubstJsixty` | +5.0 |
| `\RQfourVsNoReactionOnTimeFullResolveSubstJsixtyLo` | 2.0 | `\RQfourVsNoReactionOnTimeFullResolveSubstJsixtyHi` | 8.0 |
| `\RQfourVsNoReactionCRatioFullResolveSubstJsixty` | -0.038 | `\RQfourVsNoReactionCRatioFullResolveSubstJsixtyLo` | -0.047 |
| `\RQfourVsNoReactionCRatioFullResolveSubstJsixtyHi` | -0.029 | `\RQfourVsNoReactionDeviationFullResolveSubstJsixty` | +1.63 |
| `\RQfourVsNoReactionDeviationFullResolveSubstJsixtyLo` | 1.14 | `\RQfourVsNoReactionDeviationFullResolveSubstJsixtyHi` | 2.17 |
| `\RQfourOnTimeStableResolveSubstJsixty` | 28.6 | `\RQfourOnTimeStableResolveSubstJsixtyLo` | 25.9 |
| `\RQfourOnTimeStableResolveSubstJsixtyHi` | 31.6 | `\RQfourOnTimeDthreeStableResolveSubstJsixty` | 53.8 |
| `\RQfourOnTimeDthreeStableResolveSubstJsixtyLo` | 50.6 | `\RQfourOnTimeDthreeStableResolveSubstJsixtyHi` | 56.9 |
| `\RQfourCRatioStableResolveSubstJsixty` | 1.324 | `\RQfourDeviationStableResolveSubstJsixty` | 10.32 |
| `\RQfourNervousnessStableResolveSubstJsixty` | 391.9 | `\RQfourCostBStableResolveSubstJsixty` | 1.028 |
| `\RQfourSecondsPerRunStableResolveSubstJsixty` | 10.640 | `\RQfourOnTimeStableResolveSubstJsixtyLamZero` | 46.2 |
| `\RQfourOnTimeStableResolveSubstJsixtyLamHalf` | 30.8 | `\RQfourOnTimeStableResolveSubstJsixtyLamOne` | 23.3 |
| `\RQfourOnTimeStableResolveSubstJsixtyLamTwo` | 14.2 | `\RQfourVsNoReactionOnTimeStableResolveSubstJsixty` | +4.9 |
| `\RQfourVsNoReactionOnTimeStableResolveSubstJsixtyLo` | 1.9 | `\RQfourVsNoReactionOnTimeStableResolveSubstJsixtyHi` | 8.0 |
| `\RQfourVsNoReactionCRatioStableResolveSubstJsixty` | -0.043 | `\RQfourVsNoReactionCRatioStableResolveSubstJsixtyLo` | -0.054 |
| `\RQfourVsNoReactionCRatioStableResolveSubstJsixtyHi` | -0.032 | `\RQfourVsNoReactionDeviationStableResolveSubstJsixty` | +0.89 |
| `\RQfourVsNoReactionDeviationStableResolveSubstJsixtyLo` | 0.51 | `\RQfourVsNoReactionDeviationStableResolveSubstJsixtyHi` | 1.30 |
| `\RQfourOnTimeSentinelJsixty` | 34.3 | `\RQfourOnTimeSentinelJsixtyLo` | 31.3 |
| `\RQfourOnTimeSentinelJsixtyHi` | 37.3 | `\RQfourOnTimeDthreeSentinelJsixty` | 61.8 |
| `\RQfourOnTimeDthreeSentinelJsixtyLo` | 58.7 | `\RQfourOnTimeDthreeSentinelJsixtyHi` | 64.8 |
| `\RQfourCRatioSentinelJsixty` | 1.293 | `\RQfourDeviationSentinelJsixty` | 9.55 |
| `\RQfourNervousnessSentinelJsixty` | 129.9 | `\RQfourCostBSentinelJsixty` | 1.020 |
| `\RQfourSecondsPerRunSentinelJsixty` | 45.531 | `\RQfourOnTimeSentinelJsixtyLamZero` | 53.3 |
| `\RQfourOnTimeSentinelJsixtyLamHalf` | 37.1 | `\RQfourOnTimeSentinelJsixtyLamOne` | 27.1 |
| `\RQfourOnTimeSentinelJsixtyLamTwo` | 19.6 | `\RQfourVsNoReactionOnTimeSentinelJsixty` | +10.5 |
| `\RQfourVsNoReactionOnTimeSentinelJsixtyLo` | 7.4 | `\RQfourVsNoReactionOnTimeSentinelJsixtyHi` | 13.9 |
| `\RQfourVsNoReactionCRatioSentinelJsixty` | -0.073 | `\RQfourVsNoReactionCRatioSentinelJsixtyLo` | -0.088 |
| `\RQfourVsNoReactionCRatioSentinelJsixtyHi` | -0.060 | `\RQfourVsNoReactionDeviationSentinelJsixty` | +0.12 |
| `\RQfourVsNoReactionDeviationSentinelJsixtyLo` | -0.34 | `\RQfourVsNoReactionDeviationSentinelJsixtyHi` | 0.56 |
| `\RQfourVsNoReactionOnTimeDthreeSentinelJsixty` | +15.4 | `\RQfourVsNoReactionOnTimeDthreeSentinelJsixtyLo` | 12.5 |
| `\RQfourVsNoReactionOnTimeDthreeSentinelJsixtyHi` | 18.8 | `\RQfourVsFullResolveOnTimeSentinelJsixty` | +5.3 |
| `\RQfourVsFullResolveOnTimeSentinelJsixtyLo` | 3.3 | `\RQfourVsFullResolveOnTimeSentinelJsixtyHi` | 7.7 |
| `\RQfourVsFullResolveOnTimeDthreeSentinelJsixty` | +6.6 | `\RQfourVsFullResolveOnTimeDthreeSentinelJsixtyLo` | 4.3 |
| `\RQfourVsFullResolveOnTimeDthreeSentinelJsixtyHi` | 9.2 | `\RQfourVsFullResolveCRatioSentinelJsixty` | -0.026 |
| `\RQfourVsFullResolveCRatioSentinelJsixtyLo` | -0.033 | `\RQfourVsFullResolveCRatioSentinelJsixtyHi` | -0.019 |
| `\RQfourVsFullResolveDeviationSentinelJsixty` | -1.19 | `\RQfourVsFullResolveDeviationSentinelJsixtyLo` | -1.51 |
| `\RQfourVsFullResolveDeviationSentinelJsixtyHi` | -0.90 | `\RQfourOvertimeShareSentinelJsixty` | 0.0120 |
| `\RQfourHiredSentinelJsixty` | 3.79 | `\RQfourDeliberationsSentinelJsixty` | 55.9 |
| `\RQfourGateExitsSentinelJsixty` | 2.8 | `\RQfourRolloutsPerDeliberationSentinelJsixty` | 500 |
| `\RQfourSecondsPerDeliberationSentinelJsixty` | 0.810 | `\RQfourNeedsMetSentinelJsixty` | 5.1 |
| `\RQfourChoseNoopSentinelJsixty` | 84.5 | `\RQfourChoseOvertimeSentinelJsixty` | 1.9 |
| `\RQfourChoseReseqSentinelJsixty` | 4.9 | `\RQfourOnTimeSentinelNoOTJsixty` | 30.8 |
| `\RQfourOnTimeSentinelNoOTJsixtyLo` | 28.0 | `\RQfourOnTimeSentinelNoOTJsixtyHi` | 33.8 |
| `\RQfourOnTimeDthreeSentinelNoOTJsixty` | 57.2 | `\RQfourOnTimeDthreeSentinelNoOTJsixtyLo` | 54.0 |
| `\RQfourOnTimeDthreeSentinelNoOTJsixtyHi` | 60.3 | `\RQfourCRatioSentinelNoOTJsixty` | 1.308 |
| `\RQfourDeviationSentinelNoOTJsixty` | 9.79 | `\RQfourNervousnessSentinelNoOTJsixty` | 117.7 |
| `\RQfourCostBSentinelNoOTJsixty` | 1.011 | `\RQfourSecondsPerRunSentinelNoOTJsixty` | 44.297 |
| `\RQfourOnTimeSentinelNoOTJsixtyLamZero` | 49.6 | `\RQfourOnTimeSentinelNoOTJsixtyLamHalf` | 33.8 |
| `\RQfourOnTimeSentinelNoOTJsixtyLamOne` | 24.6 | `\RQfourOnTimeSentinelNoOTJsixtyLamTwo` | 15.4 |
| `\RQfourVsNoReactionOnTimeSentinelNoOTJsixty` | +7.1 | `\RQfourVsNoReactionOnTimeSentinelNoOTJsixtyLo` | 4.3 |
| `\RQfourVsNoReactionOnTimeSentinelNoOTJsixtyHi` | 10.2 | `\RQfourVsNoReactionCRatioSentinelNoOTJsixty` | -0.058 |
| `\RQfourVsNoReactionCRatioSentinelNoOTJsixtyLo` | -0.071 | `\RQfourVsNoReactionCRatioSentinelNoOTJsixtyHi` | -0.047 |
| `\RQfourVsNoReactionDeviationSentinelNoOTJsixty` | +0.36 | `\RQfourVsNoReactionDeviationSentinelNoOTJsixtyLo` | -0.10 |
| `\RQfourVsNoReactionDeviationSentinelNoOTJsixtyHi` | 0.79 | `\RQfourVsNoReactionOnTimeDthreeSentinelNoOTJsixty` | +10.8 |
| `\RQfourVsNoReactionOnTimeDthreeSentinelNoOTJsixtyLo` | 8.2 | `\RQfourVsNoReactionOnTimeDthreeSentinelNoOTJsixtyHi` | 13.9 |
| `\RQfourVsFullResolveOnTimeSentinelNoOTJsixty` | +1.9 | `\RQfourVsFullResolveOnTimeSentinelNoOTJsixtyLo` | 0.3 |
| `\RQfourVsFullResolveOnTimeSentinelNoOTJsixtyHi` | 3.8 | `\RQfourVsFullResolveOnTimeDthreeSentinelNoOTJsixty` | +2.0 |
| `\RQfourVsFullResolveOnTimeDthreeSentinelNoOTJsixtyLo` | 0.1 | `\RQfourVsFullResolveOnTimeDthreeSentinelNoOTJsixtyHi` | 4.3 |
| `\RQfourVsFullResolveCRatioSentinelNoOTJsixty` | -0.011 | `\RQfourVsFullResolveCRatioSentinelNoOTJsixtyLo` | -0.016 |
| `\RQfourVsFullResolveCRatioSentinelNoOTJsixtyHi` | -0.007 | `\RQfourVsFullResolveDeviationSentinelNoOTJsixty` | -0.95 |
| `\RQfourVsFullResolveDeviationSentinelNoOTJsixtyLo` | -1.23 | `\RQfourVsFullResolveDeviationSentinelNoOTJsixtyHi` | -0.69 |
| `\RQfourOvertimeShareSentinelNoOTJsixty` | 0.0000 | `\RQfourHiredSentinelNoOTJsixty` | 0.00 |
| `\RQfourDeliberationsSentinelNoOTJsixty` | 56.3 | `\RQfourGateExitsSentinelNoOTJsixty` | 2.8 |
| `\RQfourRolloutsPerDeliberationSentinelNoOTJsixty` | 466 | `\RQfourSecondsPerDeliberationSentinelNoOTJsixty` | 0.782 |
| `\RQfourNeedsMetSentinelNoOTJsixty` | 4.9 | `\RQfourChoseNoopSentinelNoOTJsixty` | 86.5 |
| `\RQfourChoseOvertimeSentinelNoOTJsixty` | 0.0 | `\RQfourChoseReseqSentinelNoOTJsixty` | 4.9 |
| `\RQfourAblOnTimeSentinelScalarised` | 26.7 | `\RQfourAblOnTimeSentinelScalarisedLo` | 22.9 |
| `\RQfourAblOnTimeSentinelScalarisedHi` | 30.8 | `\RQfourAblOnTimeDthreeSentinelScalarised` | 46.2 |
| `\RQfourAblOnTimeDthreeSentinelScalarisedLo` | 41.8 | `\RQfourAblOnTimeDthreeSentinelScalarisedHi` | 50.7 |
| `\RQfourAblCRatioSentinelScalarised` | 1.369 | `\RQfourAblDeviationSentinelScalarised` | 7.81 |
| `\RQfourAblNervousnessSentinelScalarised` | 39.3 | `\RQfourAblCostBSentinelScalarised` | 1.053 |
| `\RQfourAblVsNoReactionOnTimeSentinelScalarised` | +10.2 | `\RQfourAblVsNoReactionOnTimeSentinelScalarisedLo` | 6.9 |
| `\RQfourAblVsNoReactionOnTimeSentinelScalarisedHi` | 14.0 | `\RQfourAblVsFullResolveOnTimeSentinelScalarised` | +7.3 |
| `\RQfourAblVsFullResolveOnTimeSentinelScalarisedLo` | 4.2 | `\RQfourAblVsFullResolveOnTimeSentinelScalarisedHi` | 10.6 |
| `\RQfourAblOnTimeSentinelGate` | 22.5 | `\RQfourAblOnTimeSentinelGateLo` | 19.0 |
| `\RQfourAblOnTimeSentinelGateHi` | 26.4 | `\RQfourAblOnTimeDthreeSentinelGate` | 52.5 |
| `\RQfourAblOnTimeDthreeSentinelGateLo` | 48.0 | `\RQfourAblOnTimeDthreeSentinelGateHi` | 56.9 |
| `\RQfourAblCRatioSentinelGate` | 1.328 | `\RQfourAblDeviationSentinelGate` | 7.62 |
| `\RQfourAblNervousnessSentinelGate` | 49.8 | `\RQfourAblCostBSentinelGate` | 1.051 |
| `\RQfourAblVsNoReactionOnTimeSentinelGate` | +6.0 | `\RQfourAblVsNoReactionOnTimeSentinelGateLo` | 3.5 |
| `\RQfourAblVsNoReactionOnTimeSentinelGateHi` | 8.8 | `\RQfourAblVsFullResolveOnTimeSentinelGate` | +3.1 |
| `\RQfourAblVsFullResolveOnTimeSentinelGateLo` | 0.6 | `\RQfourAblVsFullResolveOnTimeSentinelGateHi` | 5.4 |
| `\RQfourAblOnTimeSentinelDescope` | 53.1 | `\RQfourAblOnTimeSentinelDescopeLo` | 48.7 |
| `\RQfourAblOnTimeSentinelDescopeHi` | 57.5 | `\RQfourAblOnTimeDthreeSentinelDescope` | 78.8 |
| `\RQfourAblOnTimeDthreeSentinelDescopeLo` | 74.9 | `\RQfourAblOnTimeDthreeSentinelDescopeHi` | 82.2 |
| `\RQfourAblCRatioSentinelDescope` | 1.236 | `\RQfourAblDeviationSentinelDescope` | 7.00 |
| `\RQfourAblNervousnessSentinelDescope` | 22.2 | `\RQfourAblCostBSentinelDescope` | 0.983 |
| `\RQfourAblVsNoReactionOnTimeSentinelDescope` | +36.7 | `\RQfourAblVsNoReactionOnTimeSentinelDescopeLo` | 31.0 |
| `\RQfourAblVsNoReactionOnTimeSentinelDescopeHi` | 42.1 | `\RQfourAblVsFullResolveOnTimeSentinelDescope` | +33.8 |
| `\RQfourAblVsFullResolveOnTimeSentinelDescopeLo` | 27.5 | `\RQfourAblVsFullResolveOnTimeSentinelDescopeHi` | 40.0 |
| `\RQfourAblOnTimeSentinelDeltaThree` | 21.5 | `\RQfourAblOnTimeSentinelDeltaThreeLo` | 18.0 |
| `\RQfourAblOnTimeSentinelDeltaThreeHi` | 25.3 | `\RQfourAblOnTimeDthreeSentinelDeltaThree` | 53.1 |
| `\RQfourAblOnTimeDthreeSentinelDeltaThreeLo` | 48.7 | `\RQfourAblOnTimeDthreeSentinelDeltaThreeHi` | 57.5 |
| `\RQfourAblCRatioSentinelDeltaThree` | 1.327 | `\RQfourAblDeviationSentinelDeltaThree` | 7.65 |
| `\RQfourAblNervousnessSentinelDeltaThree` | 51.1 | `\RQfourAblCostBSentinelDeltaThree` | 1.051 |
| `\RQfourAblVsNoReactionOnTimeSentinelDeltaThree` | +5.0 | `\RQfourAblVsNoReactionOnTimeSentinelDeltaThreeLo` | 2.3 |
| `\RQfourAblVsNoReactionOnTimeSentinelDeltaThreeHi` | 7.9 | `\RQfourAblVsFullResolveOnTimeSentinelDeltaThree` | +2.1 |
| `\RQfourAblVsFullResolveOnTimeSentinelDeltaThreeLo` | -1.0 | `\RQfourAblVsFullResolveOnTimeSentinelDeltaThreeHi` | 5.2 |
| `\RQfourAblOnTimeNoReaction` | 16.5 | `\RQfourAblOnTimeNoReactionLo` | 13.4 |
| `\RQfourAblOnTimeNoReactionHi` | 20.0 | `\RQfourAblOnTimeDthreeNoReaction` | 37.5 |
| `\RQfourAblOnTimeDthreeNoReactionLo` | 33.3 | `\RQfourAblOnTimeDthreeNoReactionHi` | 41.9 |
| `\RQfourAblCRatioNoReaction` | 1.395 | `\RQfourAblDeviationNoReaction` | 7.98 |
| `\RQfourAblNervousnessNoReaction` | 0.0 | `\RQfourAblCostBNoReaction` | 1.043 |
| `\RQfourAblOnTimeFullResolve` | 19.4 | `\RQfourAblOnTimeFullResolveLo` | 16.1 |
| `\RQfourAblOnTimeFullResolveHi` | 23.1 | `\RQfourAblOnTimeDthreeFullResolve` | 46.2 |
| `\RQfourAblOnTimeDthreeFullResolveLo` | 41.8 | `\RQfourAblOnTimeDthreeFullResolveHi` | 50.7 |
| `\RQfourAblCRatioFullResolve` | 1.350 | `\RQfourAblDeviationFullResolve` | 8.36 |
| `\RQfourAblNervousnessFullResolve` | 223.6 | `\RQfourAblCostBFullResolve` | 1.041 |
| `\RQfourAutoLevelZeroOnTime` | 22.5 | `\RQfourAutoLevelZeroOnTimeLo` | 17.7 |
| `\RQfourAutoLevelZeroOnTimeHi` | 28.2 | `\RQfourAutoLevelZeroNervousness` | 9.6 |
| `\RQfourAutoLevelZeroDeviation` | 6.89 | `\RQfourAutoLevelZeroSecondsPerRun` | 86.279 |
| `\RQfourAutoLevelOneOnTime` | 23.3 | `\RQfourAutoLevelOneOnTimeLo` | 18.4 |
| `\RQfourAutoLevelOneOnTimeHi` | 29.1 | `\RQfourAutoLevelOneNervousness` | 27.4 |
| `\RQfourAutoLevelOneDeviation` | 6.95 | `\RQfourAutoLevelOneSecondsPerRun` | 78.735 |
| `\RQfourAutoNoReactionOnTime` | 21.2 | `\RQfourAutoNoReactionOnTimeLo` | 16.5 |
| `\RQfourAutoNoReactionOnTimeHi` | 26.9 | `\RQfourAutoNoReactionNervousness` | 0.0 |
| `\RQfourAutoNoReactionDeviation` | 7.15 | `\RQfourAutoNoReactionSecondsPerRun` | 0.006 |
| `\RQfourAutoFullResolveOnTime` | 24.6 | `\RQfourAutoFullResolveOnTimeLo` | 19.6 |
| `\RQfourAutoFullResolveOnTimeHi` | 30.4 | `\RQfourAutoFullResolveNervousness` | 193.4 |
| `\RQfourAutoFullResolveDeviation` | 7.59 | `\RQfourAutoFullResolveSecondsPerRun` | 1.105 |
| `\RQfourAutoLevelTwoOnTime` | 29.6 | `\RQfourAutoLevelTwoOnTimeLo` | 24.2 |
| `\RQfourAutoLevelTwoOnTimeHi` | 35.6 | `\RQfourAutoLevelTwoNervousness` | 45.1 |
| `\RQfourAutoLevelTwoDeviation` | 6.92 | `\RQfourAutoLevelTwoSecondsPerRun` | 26.725 |
| `\RQfourBaseOnTimeNoReactionJthirty` | 27.0 | `\RQfourBaseOnTimeNoReactionJthirtyLo` | 25.0 |
| `\RQfourBaseOnTimeNoReactionJthirtyHi` | 29.0 | `\RQfourBaseCRatioNoReactionJthirty` | 1.356 |
| `\RQfourBaseOnTimeAlwaysSubstJthirty` | 26.6 | `\RQfourBaseOnTimeAlwaysSubstJthirtyLo` | 24.6 |
| `\RQfourBaseOnTimeAlwaysSubstJthirtyHi` | 28.6 | `\RQfourBaseCRatioAlwaysSubstJthirty` | 1.364 |
| `\RQfourBaseOnTimeFullResolveJthirty` | 31.3 | `\RQfourBaseOnTimeFullResolveJthirtyLo` | 29.3 |
| `\RQfourBaseOnTimeFullResolveJthirtyHi` | 33.4 | `\RQfourBaseCRatioFullResolveJthirty` | 1.320 |
| `\RQfourBaseOnTimeFullResolveSubstJthirty` | 30.9 | `\RQfourBaseOnTimeFullResolveSubstJthirtyLo` | 28.9 |
| `\RQfourBaseOnTimeFullResolveSubstJthirtyHi` | 33.0 | `\RQfourBaseCRatioFullResolveSubstJthirty` | 1.326 |
| `\RQfourBaseOnTimeStableResolveSubstJthirty` | 30.5 | `\RQfourBaseOnTimeStableResolveSubstJthirtyLo` | 28.5 |
| `\RQfourBaseOnTimeStableResolveSubstJthirtyHi` | 32.6 | `\RQfourBaseCRatioStableResolveSubstJthirty` | 1.329 |
| `\RQfourBaseOnTimeNoReactionJsixty` | 27.4 | `\RQfourBaseOnTimeNoReactionJsixtyLo` | 25.5 |
| `\RQfourBaseOnTimeNoReactionJsixtyHi` | 29.5 | `\RQfourBaseCRatioNoReactionJsixty` | 1.346 |
| `\RQfourBaseOnTimeAlwaysSubstJsixty` | 27.3 | `\RQfourBaseOnTimeAlwaysSubstJsixtyLo` | 25.4 |
| `\RQfourBaseOnTimeAlwaysSubstJsixtyHi` | 29.4 | `\RQfourBaseCRatioAlwaysSubstJsixty` | 1.351 |
| `\RQfourBaseOnTimeFullResolveJsixty` | 34.1 | `\RQfourBaseOnTimeFullResolveJsixtyLo` | 32.0 |
| `\RQfourBaseOnTimeFullResolveJsixtyHi` | 36.3 | `\RQfourBaseCRatioFullResolveJsixty` | 1.305 |
| `\RQfourBaseOnTimeFullResolveSubstJsixty` | 33.6 | `\RQfourBaseOnTimeFullResolveSubstJsixtyLo` | 31.5 |
| `\RQfourBaseOnTimeFullResolveSubstJsixtyHi` | 35.7 | `\RQfourBaseCRatioFullResolveSubstJsixty` | 1.312 |
| `\RQfourBaseOnTimeStableResolveSubstJsixty` | 32.2 | `\RQfourBaseOnTimeStableResolveSubstJsixtyLo` | 30.1 |
| `\RQfourBaseOnTimeStableResolveSubstJsixtyHi` | 34.3 | `\RQfourBaseCRatioStableResolveSubstJsixty` | 1.310 |
| `\RQfourSensOnTimeNoReaction` | 13.4 | `\RQfourSensOnTimeNoReactionLo` | 11.4 |
| `\RQfourSensOnTimeNoReactionHi` | 15.7 | `\RQfourSensOnTimeAlwaysSubst` | 13.8 |
| `\RQfourSensOnTimeAlwaysSubstLo` | 11.7 | `\RQfourSensOnTimeAlwaysSubstHi` | 16.1 |
| `\RQfourSensVsNoReactionOnTimeAlwaysSubst` | +0.3 | `\RQfourSensVsNoReactionOnTimeAlwaysSubstLo` | -1.1 |
| `\RQfourSensVsNoReactionOnTimeAlwaysSubstHi` | 1.8 | `\RQfourSensOnTimeFullResolve` | 15.8 |
| `\RQfourSensOnTimeFullResolveLo` | 13.7 | `\RQfourSensOnTimeFullResolveHi` | 18.3 |
| `\RQfourSensVsNoReactionOnTimeFullResolve` | +2.4 | `\RQfourSensVsNoReactionOnTimeFullResolveLo` | 0.7 |
| `\RQfourSensVsNoReactionOnTimeFullResolveHi` | 4.1 | `\RQfourSensOnTimeFullResolveSubst` | 16.4 |
| `\RQfourSensOnTimeFullResolveSubstLo` | 14.1 | `\RQfourSensOnTimeFullResolveSubstHi` | 18.8 |
| `\RQfourSensVsNoReactionOnTimeFullResolveSubst` | +2.9 | `\RQfourSensVsNoReactionOnTimeFullResolveSubstLo` | 0.9 |
| `\RQfourSensVsNoReactionOnTimeFullResolveSubstHi` | 4.8 | `\RQfourSensOnTimeStableResolveSubst` | 15.7 |
| `\RQfourSensOnTimeStableResolveSubstLo` | 13.6 | `\RQfourSensOnTimeStableResolveSubstHi` | 18.2 |
| `\RQfourSensVsNoReactionOnTimeStableResolveSubst` | +2.3 | `\RQfourSensVsNoReactionOnTimeStableResolveSubstLo` | 0.5 |
| `\RQfourSensVsNoReactionOnTimeStableResolveSubstHi` | 4.0 | `\RQfourAutoLevelThreeRuns` | 240 |
| `\RQfourAutoLevelThreeOnTime` | 33.8 | `\RQfourAutoLevelThreeOnTimeLo` | 28.1 |
| `\RQfourAutoLevelThreeOnTimeHi` | 39.9 | `\RQfourAutoLevelThreeNervousness` | 48.3 |
| `\RQfourAutoLevelThreeDeviation` | 6.67 | `\RQfourAutoLevelThreeSecondsPerRun` | 14.485 |

**RQ5** (212 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\RQfiveEventValidQwenSingle` | 84.5 | `\RQfiveEventValidQwenSingleLo` | 78.8 |
| `\RQfiveEventValidQwenSingleHi` | 88.9 | `\RQfiveEventExactQwenSingle` | 50.0 |
| `\RQfiveEventExactQwenSingleLo` | 43.1 | `\RQfiveEventExactQwenSingleHi` | 56.9 |
| `\RQfiveEventEndToEndQwenSingle` | 50.0 | `\RQfiveEventEndToEndQwenSingleLo` | 43.1 |
| `\RQfiveEventEndToEndQwenSingleHi` | 56.9 | `\RQfiveEventNoiseFpQwenSingle` | 8.8 |
| `\RQfiveEventLeaksQwenSingle` | 0 | `\RQfiveEventRawLeaksQwenSingle` | 0 |
| `\RQfiveEventAbsencePQwenSingle` | 0.472 | `\RQfiveEventAbsenceRQwenSingle` | 0.417 |
| `\RQfiveEventWorkIncreasePQwenSingle` | 0.953 | `\RQfiveEventWorkIncreaseRQwenSingle` | 1.000 |
| `\RQfiveEventNewActivityPQwenSingle` | 1.000 | `\RQfiveEventNewActivityRQwenSingle` | 0.770 |
| `\RQfiveEventReturnDayQwenSingle` | 0.520 | `\RQfiveEventValidQwenRepair` | 97.0 |
| `\RQfiveEventValidQwenRepairLo` | 93.6 | `\RQfiveEventValidQwenRepairHi` | 98.6 |
| `\RQfiveEventExactQwenRepair` | 51.0 | `\RQfiveEventExactQwenRepairLo` | 44.1 |
| `\RQfiveEventExactQwenRepairHi` | 57.8 | `\RQfiveEventEndToEndQwenRepair` | 51.0 |
| `\RQfiveEventEndToEndQwenRepairLo` | 44.1 | `\RQfiveEventEndToEndQwenRepairHi` | 57.8 |
| `\RQfiveEventNoiseFpQwenRepair` | 8.8 | `\RQfiveEventLeaksQwenRepair` | 0 |
| `\RQfiveEventRawLeaksQwenRepair` | 0 | `\RQfiveEventAbsencePQwenRepair` | 0.491 |
| `\RQfiveEventAbsenceRQwenRepair` | 0.467 | `\RQfiveEventWorkIncreasePQwenRepair` | 0.938 |
| `\RQfiveEventWorkIncreaseRQwenRepair` | 1.000 | `\RQfiveEventNewActivityPQwenRepair` | 1.000 |
| `\RQfiveEventNewActivityRQwenRepair` | 0.919 | `\RQfiveEventReturnDayQwenRepair` | 0.464 |
| `\RQfiveEventDeltaExactQwen` | +1.0 | `\RQfiveEventDeltaExactQwenLo` | +0.0 |
| `\RQfiveEventDeltaExactQwenHi` | +2.5 | `\RQfiveEventDeltaEndToEndQwen` | +1.0 |
| `\RQfiveEventDeltaEndToEndQwenLo` | +0.0 | `\RQfiveEventDeltaEndToEndQwenHi` | +2.5 |
| `\RQfiveEventValidGptOssSingle` | 87.0 | `\RQfiveEventValidGptOssSingleLo` | 81.6 |
| `\RQfiveEventValidGptOssSingleHi` | 91.0 | `\RQfiveEventExactGptOssSingle` | 75.5 |
| `\RQfiveEventExactGptOssSingleLo` | 69.1 | `\RQfiveEventExactGptOssSingleHi` | 80.9 |
| `\RQfiveEventEndToEndGptOssSingle` | 75.5 | `\RQfiveEventEndToEndGptOssSingleLo` | 69.1 |
| `\RQfiveEventEndToEndGptOssSingleHi` | 80.9 | `\RQfiveEventNoiseFpGptOssSingle` | 0.0 |
| `\RQfiveEventLeaksGptOssSingle` | 0 | `\RQfiveEventRawLeaksGptOssSingle` | 0 |
| `\RQfiveEventAbsencePGptOssSingle` | 0.967 | `\RQfiveEventAbsenceRGptOssSingle` | 0.967 |
| `\RQfiveEventWorkIncreasePGptOssSingle` | 1.000 | `\RQfiveEventWorkIncreaseRGptOssSingle` | 1.000 |
| `\RQfiveEventNewActivityPGptOssSingle` | 1.000 | `\RQfiveEventNewActivityRGptOssSingle` | 0.473 |
| `\RQfiveEventReturnDayGptOssSingle` | 0.845 | `\RQfiveEventValidGptOssRepair` | 95.5 |
| `\RQfiveEventValidGptOssRepairLo` | 91.7 | `\RQfiveEventValidGptOssRepairHi` | 97.6 |
| `\RQfiveEventExactGptOssRepair` | 82.0 | `\RQfiveEventExactGptOssRepairLo` | 76.1 |
| `\RQfiveEventExactGptOssRepairHi` | 86.7 | `\RQfiveEventEndToEndGptOssRepair` | 82.0 |
| `\RQfiveEventEndToEndGptOssRepairLo` | 76.1 | `\RQfiveEventEndToEndGptOssRepairHi` | 86.7 |
| `\RQfiveEventNoiseFpGptOssRepair` | 0.0 | `\RQfiveEventLeaksGptOssRepair` | 0 |
| `\RQfiveEventRawLeaksGptOssRepair` | 0 | `\RQfiveEventAbsencePGptOssRepair` | 0.967 |
| `\RQfiveEventAbsenceRGptOssRepair` | 0.967 | `\RQfiveEventWorkIncreasePGptOssRepair` | 1.000 |
| `\RQfiveEventWorkIncreaseRGptOssRepair` | 1.000 | `\RQfiveEventNewActivityPGptOssRepair` | 1.000 |
| `\RQfiveEventNewActivityRGptOssRepair` | 0.743 | `\RQfiveEventReturnDayGptOssRepair` | 0.845 |
| `\RQfiveEventDeltaExactGptOss` | +6.5 | `\RQfiveEventDeltaExactGptOssLo` | +3.5 |
| `\RQfiveEventDeltaExactGptOssHi` | +10.0 | `\RQfiveEventDeltaEndToEndGptOss` | +6.5 |
| `\RQfiveEventDeltaEndToEndGptOssLo` | +3.5 | `\RQfiveEventDeltaEndToEndGptOssHi` | +10.0 |
| `\RQfiveEventMessages` | 200 | `\RQfivePropValidRandom` | 100.0 |
| `\RQfivePropProposalsRandom` | 450 | `\RQfivePropCompileRandom` | 96.2 |
| `\RQfivePropDuplicateRandom` | 25.4 | `\RQfivePropWinRateRandom` | 8.7 |
| `\RQfivePropWinRateRandomLo` | 5.1 | `\RQfivePropWinRateRandomHi` | 14.3 |
| `\RQfivePropGainPRandom` | +0.036 | `\RQfivePropGainPSeRandom` | 0.021 |
| `\RQfivePropGainTRandom` | +1.020 | `\RQfivePropGainTSeRandom` | 0.282 |
| `\RQfivePropValidQwen` | 100.0 | `\RQfivePropProposalsQwen` | 255 |
| `\RQfivePropCompileQwen` | 85.5 | `\RQfivePropDuplicateQwen` | 40.4 |
| `\RQfivePropWinRateQwen` | 2.0 | `\RQfivePropWinRateQwenLo` | 0.7 |
| `\RQfivePropWinRateQwenHi` | 5.7 | `\RQfivePropGainPQwen` | +0.017 |
| `\RQfivePropGainPSeQwen` | 0.078 | `\RQfivePropGainTQwen` | +1.340 |
| `\RQfivePropGainTSeQwen` | 0.961 | `\RQfivePropVsRandomWinRateQwen` | -6.7 |
| `\RQfivePropVsRandomWinRateQwenLo` | -11.3 | `\RQfivePropVsRandomWinRateQwenHi` | -2.0 |
| `\RQfivePropVsRandomImprovementPQwen` | -0.0028 | `\RQfivePropVsRandomImprovementPQwenLo` | -0.0077 |
| `\RQfivePropVsRandomImprovementPQwenHi` | +0.0015 | `\RQfivePropVsRandomImprovementTQwen` | -0.062 |
| `\RQfivePropVsRandomImprovementTQwenLo` | -0.143 | `\RQfivePropVsRandomImprovementTQwenHi` | +0.018 |
| `\RQfivePropValidGptOss` | 96.0 | `\RQfivePropProposalsGptOss` | 441 |
| `\RQfivePropCompileGptOss` | 94.8 | `\RQfivePropDuplicateGptOss` | 1.0 |
| `\RQfivePropWinRateGptOss` | 9.3 | `\RQfivePropWinRateGptOssLo` | 5.6 |
| `\RQfivePropWinRateGptOssHi` | 15.1 | `\RQfivePropGainPGptOss` | +0.038 |
| `\RQfivePropGainPSeGptOss` | 0.017 | `\RQfivePropGainTGptOss` | +1.645 |
| `\RQfivePropGainTSeGptOss` | 0.468 | `\RQfivePropVsRandomWinRateGptOss` | +0.7 |
| `\RQfivePropVsRandomWinRateGptOssLo` | -6.0 | `\RQfivePropVsRandomWinRateGptOssHi` | +7.3 |
| `\RQfivePropVsRandomImprovementPGptOss` | +0.0004 | `\RQfivePropVsRandomImprovementPGptOssLo` | -0.0051 |
| `\RQfivePropVsRandomImprovementPGptOssHi` | +0.0052 | `\RQfivePropVsRandomImprovementTGptOss` | +0.065 |
| `\RQfivePropVsRandomImprovementTGptOssLo` | -0.060 | `\RQfivePropVsRandomImprovementTGptOssHi` | +0.205 |
| `\RQfiveExplValidQwen` | 100.0 | `\RQfiveExplValidQwenLo` | 97.5 |
| `\RQfiveExplValidQwenHi` | 100.0 | `\RQfiveExplFaithfulQwen` | 99.3 |
| `\RQfiveExplFaithfulQwenLo` | 96.3 | `\RQfiveExplFaithfulQwenHi` | 99.9 |
| `\RQfiveExplChosenCitedQwen` | 100.0 | `\RQfiveExplComponentRightQwen` | 100.0 |
| `\RQfiveExplHallucinatedQwen` | 0.00 | `\RQfiveExplWordsQwen` | 22.3 |
| `\RQfiveExplCorrectChosenActionQwen` | 150 | `\RQfiveExplCitedChosenActionQwen` | 150 |
| `\RQfiveExplCitedShareChosenActionQwen` | 100 | `\RQfiveExplCorrectPOnTimeQwen` | 9 |
| `\RQfiveExplCitedPOnTimeQwen` | 10 | `\RQfiveExplCitedSharePOnTimeQwen` | 6 |
| `\RQfiveExplCorrectTardinessQwen` | 2 | `\RQfiveExplCitedTardinessQwen` | 2 |
| `\RQfiveExplCitedShareTardinessQwen` | 1 | `\RQfiveExplCorrectBudgetOverrunQwen` | 0 |
| `\RQfiveExplCitedBudgetOverrunQwen` | 0 | `\RQfiveExplCitedShareBudgetOverrunQwen` | 0 |
| `\RQfiveExplCorrectAlternativeQwen` | 15 | `\RQfiveExplCitedAlternativeQwen` | 15 |
| `\RQfiveExplCitedShareAlternativeQwen` | 10 | `\RQfiveExplCorrectAlternativePOnTimeQwen` | 7 |
| `\RQfiveExplCitedAlternativePOnTimeQwen` | 7 | `\RQfiveExplCitedShareAlternativePOnTimeQwen` | 5 |
| `\RQfiveExplCorrectDecidingComponentQwen` | 150 | `\RQfiveExplCitedDecidingComponentQwen` | 150 |
| `\RQfiveExplCitedShareDecidingComponentQwen` | 100 | `\RQfiveExplValidGptOss` | 100.0 |
| `\RQfiveExplValidGptOssLo` | 97.5 | `\RQfiveExplValidGptOssHi` | 100.0 |
| `\RQfiveExplFaithfulGptOss` | 99.3 | `\RQfiveExplFaithfulGptOssLo` | 96.3 |
| `\RQfiveExplFaithfulGptOssHi` | 99.9 | `\RQfiveExplChosenCitedGptOss` | 100.0 |
| `\RQfiveExplComponentRightGptOss` | 100.0 | `\RQfiveExplHallucinatedGptOss` | 0.00 |
| `\RQfiveExplWordsGptOss` | 25.2 | `\RQfiveExplCorrectChosenActionGptOss` | 150 |
| `\RQfiveExplCitedChosenActionGptOss` | 150 | `\RQfiveExplCitedShareChosenActionGptOss` | 100 |
| `\RQfiveExplCorrectPOnTimeGptOss` | 150 | `\RQfiveExplCitedPOnTimeGptOss` | 150 |
| `\RQfiveExplCitedSharePOnTimeGptOss` | 100 | `\RQfiveExplCorrectTardinessGptOss` | 15 |
| `\RQfiveExplCitedTardinessGptOss` | 15 | `\RQfiveExplCitedShareTardinessGptOss` | 10 |
| `\RQfiveExplCorrectBudgetOverrunGptOss` | 29 | `\RQfiveExplCitedBudgetOverrunGptOss` | 30 |
| `\RQfiveExplCitedShareBudgetOverrunGptOss` | 19 | `\RQfiveExplCorrectAlternativeGptOss` | 148 |
| `\RQfiveExplCitedAlternativeGptOss` | 148 | `\RQfiveExplCitedShareAlternativeGptOss` | 99 |
| `\RQfiveExplCorrectAlternativePOnTimeGptOss` | 148 | `\RQfiveExplCitedAlternativePOnTimeGptOss` | 148 |
| `\RQfiveExplCitedShareAlternativePOnTimeGptOss` | 99 | `\RQfiveExplCorrectDecidingComponentGptOss` | 150 |
| `\RQfiveExplCitedDecidingComponentGptOss` | 150 | `\RQfiveExplCitedShareDecidingComponentGptOss` | 100 |
| `\RQfiveOnlineRuns` | 20 | `\RQfiveOnlineOnTime` | 5 |
| `\RQfiveOnlineOnTimeWpFive` | 5 | `\RQfiveOnlineDeltaMakespan` | -0.800 |
| `\RQfiveOnlineDeltaDeviation` | -0.617 | `\RQfiveOnlineDeltaCostB` | +0.016 |
| `\RQfiveOnlineDeliberations` | 831 | `\RQfiveOnlineProposalsAdded` | 2137 |
| `\RQfiveOnlineChosen` | 42 | `\RQfiveOnlineTokensPerRun` | 75486 |

**Data sizes and machine** (32 macros)

| Macro | Value | Macro | Value |
| --- | ---: | --- | ---: |
| `\DataRQtwoRows` | 6720 | `\DataRQtwoHours` | 0.1 |
| `\DataCalibRows` | 192000 | `\DataCalibHours` | 0.1 |
| `\DataRQthreeRows` | 230400 | `\DataRQthreeHours` | 2.2 |
| `\DataRQthreeMisspecRows` | 9600 | `\DataRQthreeMisspecHours` | 0.2 |
| `\DataRQfourBaselinesRows` | 19200 | `\DataRQfourBaselinesHours` | 3.0 |
| `\DataRQfourSensitivityRows` | 4800 | `\DataRQfourSensitivityHours` | 0.3 |
| `\DataRQfourMainRows` | 8640 | `\DataRQfourMainHours` | 9.2 |
| `\DataRQfourAblationRows` | 2400 | `\DataRQfourAblationHours` | 4.1 |
| `\DataRQfourAutonomyRows` | 720 | `\DataRQfourAutonomyHours` | 2.8 |
| `\DataRQoneRows` | 320 | `\DataRQoneHours` | 0.2 |
| `\DataRQfiveEventsRows` | 800 | `\DataRQfiveEventsHours` | 0.0 |
| `\DataRQfiveProposalsRows` | 450 | `\DataRQfiveProposalsHours` | 0.1 |
| `\DataRQfiveExplanationsRows` | 300 | `\DataRQfiveExplanationsHours` | 0.0 |
| `\DataRQfiveOnlineRows` | 20 | `\DataRQfiveOnlineHours` | 0.4 |
| `\MachineCpu` | Intel(R) Core(TM) i5-6600K CPU @ 3.50GHz | `\MachineCores` | 4 |
| `\MachinePython` | 3.12.15 | `\MachineOrtools` | 9.15.6755 |

## Commands for the owner
None required: no run is longer than a minute and nothing is recomputed. To confirm on a fresh
pull (about 40 s; PSPLIB data must be present):

```bash
uv run sentinel reproduce --check
```

A full recomputation (22.7 h recorded, in `tmux`) is printed by `uv run sentinel reproduce
--commands`.

## Open issues / next steps
- Architect: spec questions 1–3; check the macros against the summaries (`numbers.md`).
- Typeset `tab_rq1–5.tex` and the figures once in the LNCS template to confirm the width estimate
  and the 8 pt text at final size.
- `paper/generated/` is byte-identical only for the pinned matplotlib (uv.lock); an upgrade
  changes the PDF bytes, so regenerate and commit `paper/generated/` after one.
- WP8: dashboard and release package; the article and report text cite the macros.
