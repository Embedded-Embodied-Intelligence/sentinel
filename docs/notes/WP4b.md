# WP4b notes — per-newcomer handover, return epochs and the baseline policy study

**Handover per newcomer** (spec v1.6, §3; Brooks 1995). Each substitute needs
o_j = max(1, ⌈α e_j⌉) crew-member days of onboarding before it contributes (α = 0.3, e_j the
work done in full-crew days), so a SUBST that replaces m_j of M_j members adds m_j o_j
crew-member days, h_j = m_j o_j / M_j full-crew days. For a one-person activity this is the v1.2
formula. Replacing one member of a ten-person crew at e_j = 4 now costs 2 crew-member days
(0.2 full-crew days); v1.5 charged max(1, ⌈α e_j m_j / M_j⌉) = 1 full-crew day, i.e. 10
crew-member days. Without the substitute the crew loses one crew-member day per day of absence,
so replacing a member saves work in expectation when its expected remaining absence exceeds
o_j. The observation records each handover as (activity, e_j, m_j o_j crew-member days); the
belief and the deterministic forecaster replay it with the D2 shocks (§5.1, §5.2).

**Decision epochs** (§3.1 g): every day with an absence onset or return, the days after D2
shocks, D3 days and the periodic reviews. Only the epoch count of NoReaction changes: the 50
regression runs are identical without the epoch counts and flags (26 of them gain epochs, 1,685
→ 1,971 in total), and the WP2b makespans are reproduced. FullResolve(subst) re-plans and
substitutes on return days too; AlwaysSubstitute substitutes at every epoch.

**Deviation set** U'_t (§7, §7.1): the unstarted activities with p_j > 0 that were not inserted
on day t. StableResolve's second CP-SAT stage minimises Σ_{U'_t} |S_j − S_j^t|, and nervousness
counts the (epoch, activity) changes of planned starts within U'_t; milestones, the sink and
fresh D3 activities, whose planned starts nobody relies on, are left out. The realised
deviation runs over the original activities with p_j > 0; PSPLIB J30 and J60 have no real
milestones, so it equals the v1.5 value there.

**First look at T_cp = 0.1** (20 spread instances × 3 WP2b seeds per set, λ_A = 0.01, E[L] = 3,
δ_D = 0.2; means per run; not a study, no intervals):

| Set | Policy | On time (WP4a) | C / C* (WP4a) | Deviation d | Nervousness | Substituted | Handover d | Onboarding d / subst. | RESEQs | s / run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | NoReaction | 0.217 (0.217) | 1.379 (1.379) | 7.76 | 0 | 0 | 0 | -- | 0 | 0.005 |
| J30 | AlwaysSubstitute | 0.183 (0.050) | 1.386 (1.557) | 7.96 | 0 | 25.2 | 3.4 | 1.93 | 0 | 0.010 |
| J30 | FullResolve | 0.250 (0.233) | 1.339 (1.338) | 8.03 | 210.6 | 0 | 0 | -- | 62.3 | 1.737 |
| J30 | FullResolve(subst) | 0.233 (0.083) | 1.351 (1.485) | 8.45 | 218.8 | 25.0 | 3.5 | 1.93 | 63.1 | 1.774 |
| J30 | StableResolve(subst) | 0.250 (0.067) | 1.347 (1.492) | 8.09 | 187.9 | 24.7 | 3.3 | 1.87 | 62.8 | 2.894 |
| J60 | NoReaction | 0.167 (0.167) | 1.410 (1.410) | 10.56 | 0 | 0 | 0 | -- | 0 | 0.009 |
| J60 | AlwaysSubstitute | 0.150 (0.067) | 1.426 (1.553) | 10.96 | 0 | 45.7 | 6.2 | 1.87 | 0 | 0.019 |
| J60 | FullResolve | 0.217 (0.167) | 1.369 (1.371) | 12.17 | 785.8 | 0 | 0 | -- | 97.6 | 8.824 |
| J60 | FullResolve(subst) | 0.167 (0.083) | 1.369 (1.498) | 12.46 | 807.4 | 44.5 | 6.2 | 1.88 | 97.7 | 9.042 |
| J60 | StableResolve(subst) | 0.167 (0.083) | 1.369 (1.512) | 12.01 | 512.8 | 45.6 | 6.2 | 1.87 | 97.4 | 14.792 |

In brackets the WP4a values (J30 at T_cp = 0.5, J60 at 0.05, v1.5 handover). Substitution
no longer lengthens projects: handovers add 3.4 (J30) and 6.2 (J60) full-crew days per run
instead of 26 and 48, about 1.9 crew-member days per replaced member. It does not help either:
AlwaysSubstitute stays slightly below NoReaction, and FullResolve without substitution is on
time most often. StableResolve(subst) changes fewer planned starts than FullResolve(subst), 188
vs 219 (J30) and 513 vs 807 (J60), at the same C / C*. NoReaction has 69.0 / 105.6 epochs per
run (53.5 / 84.1 in WP4a) because returns are epochs; its makespans equal WP2b's (0
mismatches in 120 runs). 0 CP-SAT fallbacks in 38,477 stages. The 300 runs per set took
163.5 s (J30) and 614.0 s (J60) on 4 workers.

**RQ4 study** (docs/experiments/plan.md). Every 4th instance of J30 and J60 (120 per set),
λ_A ∈ {0, 0.005, 0.01, 0.02}, E[L] = 3, four WP2b replications, the five policies with common
random numbers; on time evaluated post hoc for δ_D ∈ {0.2, 0.3}; sensitivity E[L] = 5 for J30.
Paired differences against NoReaction share the world (instance, scenario, replication), and
their 95 % intervals come from a cluster bootstrap over instances (1,000 resamples).

**References.** Brooks 1995; Van de Vonder et al. 2007; Herroelen & Leus 2005; Wilson 1927;
Davison & Hinkley 1997.
