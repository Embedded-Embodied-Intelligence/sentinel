# WP7 notes — paper artifacts, RQ1 error analysis, reproducibility

**RQ1 error analysis (method).** The narrator now exposes, per true precedence edge, its
phrasing (`narrate.edge_phrasings`): the side whose block states it (narrative: successor
"It can only start once A is done." or predecessor "It must be finished before C begins.", each
with probability 1/2; structured: always the successor's predecessor list), the number form of
the stating block's duration (words with probability 1/2) and the paragraph distance between
the blocks of the two activities (narrative paragraphs hold 1–3 shuffled blocks; structured: one
block per activity in topological order). The texts are unchanged (SHA-256 of the 80 study
texts). Each session of run `results/wp6/20261023-215350-f5aad526` is replayed from its bundle
(replay mode; all 640 round rows reproduce every score column) and every true edge between
matched activities (the edges of edge recall) is marked found or missed after rounds 0–3.
Recall is pooled over the sessions of a backend, style and round; 95 % percentile intervals of
a cluster bootstrap over the 40 instances (2,000 resamples, seed key `wp6_rq1_errors`).

**RQ1 error analysis (finding).** In the narrative style, dependencies stated on the
predecessor's side are the ones missed: gpt-oss-120b recalls 0.942 [0.922, 0.958] of the
successor-side edges but 0.526 [0.487, 0.567] of the predecessor-side ones (round 0), so 88.1 %
[84.6, 91.3] of its 512 missed edges are predecessor-side, against a base share of 47.7 %;
qwen2.5:7b: 0.902 against 0.117, 89.7 % of 729 missed. Repair rounds change nothing (round 3:
87.6 % and 89.6 %): the validator cannot flag a missing edge, since an answer without it is
still a valid instance. Within the successor side, distance has no effect (0.93–0.97); within
the predecessor side gpt-oss-120b drops from 0.69 (same paragraph) to about 0.5 at three or
more paragraphs. The number form has no effect (0.750 words, 0.737 digits). The side is
randomised per edge, so the effect is causal for these texts; the prompt already says that both
phrasings make A a predecessor of B.

**Paper pipeline.** `configs/paper.toml` → verified runs (manifest present, completed, not
smoke, `git_dirty: false`, SHA-256 of manifest and raw outputs pinned, summary-manifest inputs
consistent) → summary tables read by section, caption, row key and column → 1,430 macros (value
as printed; comment `file:line | table | row | column`), five booktabs tables, six figures, in
English and Polish (decimal comma `{,}`, interval separator `;`, Polish labels) →
`paper/generated/MANIFEST.json` (generator commit, inputs and outputs with SHA-256). Values no
summary prints: Sentinel full (autonomy level 3) on the 240 worlds of the autonomy study,
33.8 % [28.1, 39.9] on time, from the main run's rows through `policy_summary.aggregate`
(checked: the same code reproduces the summary's pooled J30 row exactly).

**Macro names.** Letters only: `RQ<one..five>` + metric + subject + set (`Jthirty`, `Jsixty`)
+ λ_A (`LamZero`, `LamHalf` 0.005, `LamOne` 0.01, `LamTwo` 0.02; none = pooled) or checkpoint
(`Fzero`, `Ffour`, `Feight`); `Lo`/`Hi` for interval bounds, e.g. `\RQfourOnTimeSentinelJthirty`,
`\RQfourVsNoReactionOnTimeSentinelJthirtyLo`, `\RQthreeBrierMcFullJsixtyFfour`,
`\RQoneErrMissedPredecessorGptOssRoundZero`; backends `Qwen` and `GptOss`, sources `Random`;
`Calib…` (scenario calibration), `Data…` (rows, hours per run), `Machine…`.

**Figures.** Palette and inks of the WP3–WP5 figures (policy colour slots in registry order,
Sentinel variants one slot with markers `o`/`H`), a marker and line style per series, direct
labels with leader lines where points cluster (RQ4), a legend only where lines coincide (RQ1),
all text 8 pt at 12.2 cm or 5.8 cm; RQ4's two sets are stacked so that labels have the full
width. Table widths are estimated from STIX glyph advances + 10 % (no TeX on the server):
at most 334 pt of 347 pt.

**Reproduce.** `sentinel reproduce --check` regenerates 117 files (91 summary files of the 14
runs and the 26 paper files) in about 40 s and compares bytes, provenance pinned from the
committed manifests; `--commands` prints the prerequisites and the 14 recorded commands
(22.7 h in total) with keyless `--cache-file` replays for the five LLM runs.
