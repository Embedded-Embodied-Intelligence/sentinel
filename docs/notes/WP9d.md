# WP9d notes — one comparison for decision, display and explanation in the application

**Purpose.** v2.0.2 kept the decision of §6 and showed figures from a second evaluation on the
overview's worlds, so a page could rank an alternative above the recommended action, and an
explanation (written from the deliberation's record) could cite numbers the page did not show.
The architect's answers to the WP9c questions remove both in the application; §6 and the research
runs are unchanged (v2.0.3, §11.5–§11.7).

**The rule as implemented (`AppSentinel`, `app/planning.py`).** A subclass of the research
`Sentinel` replaces only `deliberate`, so epochs, approvals and the permission gate stay shared:

1. The needs of NOOP (§5) are read on the 200 sampled worlds of the forecast of the day,
   `derive_seed(project seed, "forecast", t)`; NOOP's rollouts are the overview's.
2. Racing stage 1 stays that of §6: `N₁ = 25` rollouts with `derive_seed(project seed, "sentinel",
   t)` and the same criterion (`stage_one` equals `race`, by test).
3. The comparison replaces stage 2: the survivors, NOOP and, while fewer than six candidates are
   in, the best of those dropped go onto the 200 worlds (`comparison_set`).
4. `choose`, the research rule with its materiality ties, runs on that comparison with paired
   standard errors over the 200 worlds; a dropped candidate in it competes and may win.
5. The record holds the comparison's figures; candidates outside it keep their stage 1 figures,
   marked dropped, and are never shown.

Parameters are those of §8 (`θ_D = 0.8`, `ε_D = 0.02`, `ε_T = 0.5`, `ε_B = 0.01`, `ε_Δ = 0.5`), with
`N = 200` in place of `N = 100`.

**Why the numbers now match to the digit.** With 200 worlds a chance is `k/200`, so half of all
values end in a half per cent. The page rounded half up on a binary product, the template and the
record's rendering rounded the binary value (`.2f`): 0.585 was 59 % on the page and 58 % in the
explanation. One rule now serves all: `half_up`, with the noise of the binary fraction removed
first (`Texts.pct`, `Texts.decimal`, `shown_chance`). Both explanations read
`Recommendation.as_shown`, the record restricted to the rows shown with chances in whole per cent
and delays in tenths, so the faithfulness check of §10.4 treats any other figure, a stage 1 figure
included, as made up.

**The sentence (§11.5 item 7, §11.7).** It appears exactly when the deciding component comes
after `min(p̂, θ_D)` or the candidate order decides. It has two openings: "Similar chance (the
difference is within the uncertainty)" and, where the chosen action and the runner-up both reach
`θ_D − ε_D`, "Both options reach the target chance", since there the cap of the rule, not
uncertainty, makes them tie (95 % against 82 % is not "similar"). The second half names the
component. On the simulator it follows the decision on the timeline.

**What the rule changes in practice.** On 15 J30 worlds run to the end with the simulator's settings at
autonomy 2 (`scripts/bench_app_rule.py`; informal, not a study), both rules finish on time in 2 of
15, with 13.27 (application) and 12.87 (research) mean days late; the application finishes earlier
in 2 worlds, the same in 10 and later in 3. On the J60 example it finishes at 81 against 85
(deadline 83). Of 704 deliberations, a component after the chance decided 630; alternatives with a
higher chance than the choice were shown 270 times, none significantly better in a pair; no
candidate dropped in stage 1 won. A later component is the common case: under the rule's thresholds
the best chances usually tie.

**Cost.** A survivor now gets 200 rollouts instead of 100, and stage 1 and the needs gate use
their own: 2.3 times the rollouts and twice the time (865 s against 433 s over the 15 worlds; the
small example 25 s → 50 s, the J60 example 84 s → 180 s). A live recommendation costs about what
it did, since v2.0.2 already evaluated the shown candidates on 200 worlds after deciding; the
showcase's log took 0.68 s against 0.84 s.

**Limitations for the paper.** The application's decisions are no longer those of the research
agent: RQ4 and RQ5 results describe §6, not this rule, and the simulator page says so. A simulator
project replays its advances, so one created before 1.1.1 gives a different run after the upgrade.
Rule (6) filters against the best of the current set, so a choice can tie with the best while being
significantly behind another candidate in a pair; this did not occur in the sample above, and the
page's sentence would cover it.
