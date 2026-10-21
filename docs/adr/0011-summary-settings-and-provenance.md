# ADR-0011: Summary settings on regeneration, reference rows and summary provenance

- Status: accepted
- Date: 2026-10-21
- WP: WP3b.1

## Context

WP3b.1 changes only the summaries of two committed forecast runs: new metrics, new tables, and
reference rows in the misspecification run taken from the main run (same seeds, same worlds).
`manifest.json` and `forecasts.csv.gz` must not change, yet the summariser read its whole
config, `[summary]` included, from the manifest, which cannot name the reference run.
Regenerated summaries must also say which code produced them. `summary.md` and the LaTeX tables
were byte-identical across regenerations, and the figures must stay so.

## Decision

On regeneration the run parameters come from the manifest, and the `[summary]` section comes
from the config file in the manifest's `config_path` when all of that file's other keys equal
the manifest's config; otherwise the manifest's own section is used. Every summary records its
origin in `summary_manifest.json`: generating commit, dirty flag (changes under `results/` do
not count), time, the settings used and their source, and the SHA-256 of every file read.
`summary.md` names the commit. Reference rows are appended as further forecasters after a join
on (set, instance, scenario, replication, f) that checks world seed, forecast seed and
makespan. They keep the randomised PIT values of their own run, and figures show only the
run's own forecasters.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Edit `manifest.json` to add the reference run | Forbidden by the WP; the manifest describes the run as it happened |
| CLI flag `--reference <run>` | The WP fixes the command `sentinel summarise-forecasts <run_dir>`; a flag is easy to forget and is not part of the config |
| Always take `[summary]` from the config file | A config edited for a new study would silently re-summarise an old run with mismatched settings |
| Find the reference run by scanning `results/` | Implicit; two candidate runs would be ambiguous |
| Draw new PIT values for reference rows | The same row would score differently in the two summaries |
| Timestamp and file hashes in `summary.md` | Breaks byte-identical regeneration; they live in `summary_manifest.json` instead |

## Consequences

- Summary-only settings added later (metrics, tables, references) apply to existing runs
  without touching their manifests. Changing a run key in the config file makes old runs fall
  back to their manifest's settings; `summary_settings_source` shows which applied.
- Config hashes of future runs from these configs differ from the committed runs' hashes,
  because the `[summary]` sections gained keys.
- Only the timestamp in `summary_manifest.json` changes between regenerations at one commit.
  `detect-secrets` skips these files, as it does the run manifests.
- Summarising the misspecification run reads the 230,400-row main file (≈ 6 s in total).
