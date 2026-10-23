# RQ5 explanations — run 20261023-215349-21617c9c

150 decision states; shares in % with 95 % Wilson intervals.

| Backend | Model | Valid | Fully faithful | Chosen cited | Component right | Hallucinated numbers / expl. | Words (mean) | Over 80 words | Tokens / expl. | Latency (s) |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: |
| ollama | qwen2.5:7b | 100.0 [97.5, 100.0] | 99.3 [96.3, 99.9] | 100.0 [97.5, 100.0] | 100.0 [97.5, 100.0] | 0.00 | 22.3 | 0.0 [0.0, 2.5] | 824 | 6.7 |

Cited facts per kind: correct / cited (share of explanations citing the kind).

| Backend | chosen_action | p_on_time | tardiness_days | budget_overrun | alternative | alternative_p_on_time | deciding_component |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ollama | 150/150 (100 %) | 9/10 (6 %) | 2/2 (1 %) | 0/0 (0 %) | 15/15 (10 %) | 7/7 (5 %) | 150/150 (100 %) |
