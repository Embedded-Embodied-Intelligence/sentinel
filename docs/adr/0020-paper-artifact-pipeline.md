# ADR-0020: Paper artifacts from summary cells, pinned runs and a byte-identity check

- Status: accepted
- Date: 2026-10-24
- WP: WP7

## Context

After WP6 nothing is recomputed: the article (English, LNCS) and the course report (Polish)
must take every number, table and figure from the 14 committed runs (invariant 2), cite numbers
through generated LaTeX macros, and a reader must be able to check that the committed results
regenerate. The summaries (`summary.md`) already print every statistic with its rounding; run
manifests record no hashes of their data files; summary writers record the commit and time of
their generation; no LaTeX is installed on the server.

## Decision

`configs/paper.toml` lists the runs by role and pins the SHA-256 of each manifest and raw
output. `sentinel paper` takes every macro value from a cell of a summary table, as printed,
addressed by section, caption, row key and column (`summary_tables`), and the comment above each
macro names that cell (file:line); the few values no summary prints (the autonomy level 3 on the
ablation worlds) come from the run's rows through the summary's own reader and aggregation.
`sentinel reproduce --check` regenerates every summary of the paper runs and `paper/generated/`
in temporary copies, with the provenance (commit, time) taken from the committed summary
manifest and `MANIFEST.json`, and compares bytes.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Recompute statistics in the generator from `results.csv` | A second implementation of each statistic could round or define differently from the summaries the reports cite |
| Pin hashes in the run manifests | Changes committed result files (forbidden); `summary_manifest.json` covers only WP3–WP6 inputs |
| Compare regenerated files modulo provenance lines | Weaker than byte identity; provenance pinning keeps the comparison exact |
| Macros for every summary cell | Thousands of unreadable names; the catalogue covers what the texts cite (1,430 macros) |
| Check table widths by compiling LaTeX | No TeX on the server; a test estimates widths from STIX glyph advances + 10 % for Computer Modern |

## Consequences

A summary must stay readable by `summary_tables` (Markdown tables with unique row keys); a new
statistic for the texts is added to its summary first, then to the catalogue. Regenerated
summaries are committed when their code changes (WP7 regenerated the five policy summaries,
whose run-time manifests lacked the inputs `regenerate` records). The RQ1 summary and thus
`reproduce --check` need `data/psplib` (the error analysis narrates the texts). Figures read
summary cells or raw rows only; their PDFs carry no creation date, so regeneration is
byte-identical for a fixed matplotlib version.
