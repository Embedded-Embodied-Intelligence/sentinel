# ADR-0013: Policy study layout and paired statistics

- Status: accepted
- Date: 2026-10-21
- WP: WP4b

## Context

RQ4 compares five policies (spec §7) on the same worlds: (set, instance, scenario,
replication) with common random numbers, the NoReaction worlds being WP2b's. A run takes from
5 ms (NoReaction) to about a minute (StableResolve(subst) on a hard J60 instance at
T_cp = 0.1), so one J60 instance with all scenarios, replications and policies takes about
10 minutes. WP7 will add Sentinel on the same worlds. Runs of one instance are correlated (same
network, baseline plan and C*), and the policies are compared on identical worlds. The
trade-off figure plots five policies; the reference palette tells at most three series apart in
a scatter (dataviz, all-pairs check).

## Decision

One pool task per (instance, scenario) runs every replication and policy in debug mode with the
realised schedule checked; results.csv.gz holds one raw row per run. The summaries give on-time
shares with Wilson intervals over the runs of a cell, as in WP2b, and paired differences
against a reference policy over the same worlds with a cluster bootstrap over the instances of
a set (one resample matrix per set, shared by all statistics; 1,000 resamples), as in WP3b. The
trade-off figure has one panel per policy, with the reference policy in grey.

## Alternatives considered

| Option | Why not |
| --- | --- |
| One task per instance (WP2b, WP3b) | 240 tasks of up to 10 min: a long tail on 4 workers and coarse progress |
| One task per run | 19,200 tasks: instance and baseline loaded per run, IPC dominates the cheap policies |
| Bootstrap or Wilson intervals over runs for differences | Runs of an instance are correlated; intervals would be too narrow, and unpaired ones ignore the common worlds |
| Paired tests per cell (t, Wilcoxon) | Also ignore the clustering by instance; the bootstrap gives intervals for every statistic from the same resamples |
| One scatter panel per set with five colours | Two of the five categorical slots cannot be told apart in a scatter; identity would rest on markers alone |

## Consequences

- Every policy has the same worlds, so a paired difference of means equals the difference of
  the policies' means; the LaTeX table shows only the intervals in its second rows.
- WP7 can add Sentinel rows to the same worlds and reuse the summariser with the same reference
  policy. Summaries regenerate from results.csv.gz (`sentinel summarise-policies`).
- Wilson intervals of on-time shares understate the uncertainty across instances; summary.md
  says so, and the paired differences carry the cluster intervals.
- A run's on-time flags for every δ_D come from one simulation, which is exact only because no
  compared policy uses the deadline; a deadline-aware policy (Sentinel) needs one run per δ_D.
