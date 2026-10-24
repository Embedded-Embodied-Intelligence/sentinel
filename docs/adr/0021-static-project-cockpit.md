# ADR-0021: A static project cockpit from re-simulated study worlds

- Status: accepted
- Date: 2026-10-24
- WP: WP8

## Context

The presentation promised a dashboard of the plan, the risk and the agent's decisions, and the
course deliverable is a zip that must open on any machine. No new runtime dependency is allowed
and no experiment is recomputed. The committed WP5 results hold per-run counts, not plans,
events or decision records; a run is deterministic from its seed and parameters (the WP6b
reruns reproduced WP5 exactly). `DecisionRecord` keeps NOOP's p̂ per deliberation but no
makespan quantiles; the RQ5 caches and decision states depend on its rendered form.

## Decision

`sentinel dashboard` re-simulates one world of the studies (world settings of
`configs/wp5_rq4_main.toml`, WP2b seed of the replication, the WP4 baselines by registry name
and the Sentinel variants by their WP5 study names, so a study row is reproduced) under two
policies, and writes one HTML file: inline CSS, hand-built inline SVG, a few lines of vanilla
JavaScript, no URL and no timestamp. The risk chart repeats NOOP's rollouts of every
deliberation on the agent's own worlds (its epoch seed and rollout count), so P(C ≤ D) equals
the record's (checked) and gives the P10–P90 band. Explanations are a template built from the
record alone and checked like an LLM answer (spec §10.4); `--explain ollama|openrouter` uses the
RQ5 explanation settings through the record/replay cache, after the runs.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A served dashboard (Streamlit, Dash, a local web server) | New runtime dependency; does not open from the zip offline |
| A JavaScript chart library | External file or URL; heavier than the charts need |
| matplotlib SVG inside the page | Ids, metadata and font handling to tame for byte identity and size; hover and filtering still need markup of our own |
| Quantiles added to `DecisionRecord` | Changes the agent's records and their rendered form (RQ5 prompts, cache keys, stored decision states) for a view |
| A separate forecaster for the risk chart | Its numbers would differ from the ones the agent decided on |
| Rows read from the committed results | They hold counts only; the Gantt and the log need the run itself |

## Consequences

A cockpit costs one run of each policy plus NOOP's rollouts per deliberation (J30 about 10 s,
J60 about a minute) and is byte-identical for the same command at the same commit and software.
The cockpit package may import the LLM layer and the interpretation layer; no simulation, agent
or policy module may import it (the import test covers `sentinel.dashboard`). A change of the
engine or the agent changes the cockpits, which the example script detects by checking each
example against its WP5 row.
