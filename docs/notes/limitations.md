# Limitations and threats to validity (WP0–WP6)

Collected in WP7 for the article and the course report, one paragraph each, with the report
where the issue was found or measured. Numbers come from the committed runs
(`configs/paper.toml`, macros in `paper/generated/numbers.tex`).

**Synthetic disruptions.** The disruptions D1–D3 (absences, work increases, new activities;
spec §2.2) are drawn from stated distributions, not fitted to real software projects. The
rates were chosen by the architect so that the base policy is on time "often but not always"
(`docs/experiments/plan.md`, run `results/wp2/20261020-181559-6534a712`); D2 and D3 alone
raise C / C* from 1.10 to 1.25 (J30), so the deadlines δ_D ∈ {0.2, 0.3} are tight by design.
Conclusions hold for this scenario family; other rates (e.g. δ_D = 0.1, excluded because
NoReaction is almost never on time) may order the policies differently.
([WP2a.1](../reports/WP2a.1.md), [WP2b](../reports/WP2b.md))

**PSPLIB resources read as IT roles.** The four renewable resources of PSPLIB become the
backend developer, frontend developer, tester and DevOps engineer, and resource units become
workers with names and absences (spec §1.1). PSPLIB teams are far larger than real IT teams
(36–219 workers in J30), activities have generated durations of 1–10 days, and precedence
networks are random, so "software project" is a reading of the benchmark, not data from
software projects. ([WP0](../reports/WP0.md), [WP6a](../reports/WP6a.md), spec question 3)

**Synthetic texts.** RQ1's project descriptions and RQ5's team messages are written by
deterministic templates with a seeded vocabulary and a fictional roster, so that the ground
truth is exact and no LLM writes the inputs. Real descriptions and messages are longer, less
regular and ambiguous; the extraction and parsing rates are upper bounds of a kind. The
templates also confound phrasing features: the RQ1 error analysis shows that dependencies stated
on the predecessor's side ("A must be finished before C begins") account for 88 % of the edges
gpt-oss-120b misses, a property of this narrator's phrasings. Since the side of each
dependency is randomised, that effect is causal for these texts.
([WP6a](../reports/WP6a.md), [WP6b](../reports/WP6b.md), [WP7](../reports/WP7.md))

**Compounding work increases.** A work increase D2 multiplies the remaining work, so in
expectation remaining work R grows when R exceeds 1 / (λ_S (E[F] − 1)) (167 full-crew days at
λ_S = 0.01): the makespan distribution has a heavy right tail. One of 20,000 rollouts of a
misspecified forecaster reached the day limit in a smoke run; no committed world was
truncated, but the tail inflates CRPS and means. ([WP3b](../reports/WP3b.md), spec question 5)

**Railway semantics and no early completion.** Activities never start before their planned
day (spec §3), so the realised makespan is never below the planned one and finishing early is
not rewarded. This favours stable plans and makes "on time" depend on the baseline plan's
slack. ([WP2a](../reports/WP2a.md), spec question 5)

**CP-SAT deterministic time against wall time.** RQ2 compares methods under wall-clock
limits (1 s and 10 s, one worker) on one machine, so its runtimes and the share of proven
optima depend on that CPU. Everywhere inside simulations (baseline plans, RESEQ, FullResolve)
CP-SAT stops at a deterministic time limit (5 deterministic s for the baseline plans, 0.1 per
stage in policies) for common random numbers; deterministic seconds are not seconds, and
another OR-Tools version may change both the work per deterministic second and the plans.
([WP1](../reports/WP1.md), [WP2b](../reports/WP2b.md), ADR-0006, ADR-0008)

**Reference makespans.** C* is the J30 optimum but only the best known value for J60 (`hrs`),
so J60 gaps and the deadline D = ⌈(1 + δ_D) C*⌉ rest partly on heuristic references; the
`j60_lb` file lacks entries for 70 instances. ([WP0](../reports/WP0.md), [WP1](../reports/WP1.md))

**One machine.** Every committed run was recorded on one server (Intel i5-6600K, 4 logical
cores, WSL2; `docs/infra/environment.md`), with Ollama on a GTX 1060. Seconds per run, per
deliberation and per LLM call are measurements of that machine; only the results that do not
depend on time (makespans, choices, scores) transfer. Time-dependent behaviour is excluded by
design: no policy decision uses wall time. ([WP5b](../reports/WP5b.md), [WP6a](../reports/WP6a.md))

**Instance subsets and replications.** The Sentinel studies use every 4th J30 instance and every
8th J60 instance with R = 4 replications (the baseline study every 4th of both), the ablation
every 8th J30 instance, the autonomy
levels 0 and 1 only at λ_A = 0.01, and RQ1 every 12th J30 instance; the subsets were set by
the time budget. On-time shares carry Wilson intervals over runs, which understate the
uncertainty across instances; the paired differences use a cluster bootstrap over instances.
([WP4b](../reports/WP4b.md), [WP5b.1](../reports/WP5b.1.md))

**Different day limits.** Sentinel runs stop at 5 D(0.2), the baselines at 5 D(0.3); a
truncated run counts as late. No committed run was truncated, so the difference has no effect
on the results. ([WP5a](../reports/WP5a.md))

**OpenRouter and Groq answer variance.** The cloud model, `openai/gpt-oss-120b`, was served by
Groq through OpenRouter with the provider pinned (no fallback). Hosted answers vary between
identical requests and system fingerprints, and through OpenRouter one resent request used
about twice the completion tokens of the direct-Groq answer. A live rerun would not reproduce
the texts; the committed replay bundles are the reference, and the local model
(`qwen2.5:7b`, weights pinned by digest) is the reproducible one.
([WP6a](../reports/WP6a.md), [WP6c](../reports/WP6c.md))

**One decoding setting per backend.** Every LLM call uses temperature 0, one seed per item and
at most 3 repair rounds; with deterministic decoding qwen2.5:7b repeats its previous answer in
most narrative repair rounds (2.45 of 2.92 rounds per session unchanged). Other temperatures, prompts or repair
designs were not studied, so "repair does not help" is a statement about this protocol.
([WP6a](../reports/WP6a.md))

**The faithfulness check's scope.** An explanation is faithful when every cited fact equals
the decision record (numbers within the rounding of the written value), the chosen action and
the deciding component are cited and right, and every number written in digits in the summary
matches the record. Number words are not checked, the meaning of the prose is not judged, and
no person read the explanations: faithfulness is not usefulness. ([WP6b](../reports/WP6b.md))

**Offline evaluation of proposals.** LLM proposals are judged on 150 recorded decision states
(one replication of the ablation subset, stratified sample) by racing them with the rule's
candidates on the recorded epoch's worlds. A win changes one deliberation; its effect on whole
runs is measured only by the small online check. ([WP6b](../reports/WP6b.md))

**The small online check.** Sentinel with gpt-oss-120b proposals at every gated deliberation
ran on 20 worlds (J30 every 24th, λ_A = 0.01, one replication, one backend): 5 of 20 on time,
as in WP5, with mean differences without intervals. It shows that the online path works and
what it costs, not that proposals change outcomes. ([WP6c](../reports/WP6c.md))

**DESCOPE as a demonstration.** The DESCOPE variant may drop the three real activities whose
only successor is the sink (spec §4), so it finishes less work; none of the baselines can do
that. Its on-time share is not comparable with the others' and is reported as a demonstration
of the permission gate and the scope goal only. ([WP5b](../reports/WP5b.md), plan.md)

**Privacy safeguards are tested, not audited.** No field of the event schema can hold a
reason, accepted events never contained one (0 leaks), and with `store_prompts = false` cache
records keep no message text and an invalid answer only its issue list (WP7). These checks run
on synthetic messages; no real data were processed, and a schema-valid answer could still put
free text into a name field. ([WP6b](../reports/WP6b.md), [WP6c](../reports/WP6c.md), ADR-0018)
