# RQ5 proposals — run 20261023-215212-bdb0c248

150 decision states; sources random, ollama. Shares in % with 95 % Wilson intervals; gains as mean ± standard error over the states a source wins (min(p, theta_D) higher and expected tardiness lower are positive).

| Source | Model | Valid answers | Proposals | Compile rate | Duplicate rate | Win rate | Gain min(p, θ) | Gain T (days) | Tokens / state | Latency / state (s) |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: | ---: |
| random | uniform | 100.0 [97.5, 100.0] | 450 | 96.2 [94.0, 97.6] | 25.4 [21.5, 29.7] | 8.7 [5.1, 14.3] | +0.036 ± 0.021 | +1.020 ± 0.282 | 0 | 0.0 |
| ollama | qwen2.5:7b | 100.0 [97.5, 100.0] | 255 | 85.5 [80.6, 89.3] | 40.4 [34.1, 47.0] | 2.0 [0.7, 5.7] | +0.017 ± 0.078 | +1.340 ± 0.961 | 1380 | 6.9 |

Win rate by stratum of the rule's own choice (NOOP or an action).

| Source | Rule chose NOOP | Rule chose an action |
| --- | --- | --- |
| random | 6.7 [2.9, 14.7] (n = 75) | 10.7 [5.5, 19.7] (n = 75) |
| ollama | 1.3 [0.2, 7.2] (n = 75) | 2.7 [0.7, 9.2] (n = 75) |

Issues: ollama:not_eligible 25, ollama:out_of_range 5, ollama:rejected 7, random:rejected 17.

Wins where the source's race dropped the rule's own choice in stage 1 (racing on N_1 rollouts, spec section 6): random 1, ollama 0.

LLM - random, paired by state (95 % bootstrap interval over states): win rate in percentage points, and the mean improvement per state (0 where the source does not win) in min(p, theta_D) and in T.

| Source | Win rate | Improvement min(p, θ) | Improvement T (days) |
| --- | --- | --- | --- |
| ollama | -6.7 [-11.3, -2.0] | -0.0028 [-0.0077, +0.0015] | -0.062 [-0.143, +0.018] |
