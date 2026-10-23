# RQ5 event parser — run 20261023-220452-f8a335f4

200 messages, backends ollama, openrouter. Shares in % with 95 % Wilson intervals.

| Backend | Condition | Valid | Exact | End to end | Noise false positives | Leaks | Raw leaks | Rounds | Tokens / msg | Latency / msg (s) |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| ollama | single_shot | 84.5 [78.8, 88.9] (n = 200) | 50.0 [43.1, 56.9] (n = 200) | 50.0 [43.1, 56.9] (n = 200) | 8.8 [3.0, 23.0] (n = 34) | 0 | 0 | 0.00 | 1471 | 6.5 |
| ollama | repair | 97.0 [93.6, 98.6] (n = 200) | 51.0 [44.1, 57.8] (n = 200) | 51.0 [44.1, 57.8] (n = 200) | 8.8 [3.0, 23.0] (n = 34) | 0 | 0 | 0.23 | 1844 | 7.4 |
| openrouter | single_shot | 87.0 [81.6, 91.0] (n = 200) | 75.5 [69.1, 80.9] (n = 200) | 75.5 [69.1, 80.9] (n = 200) | 0.0 [0.0, 10.2] (n = 34) | 0 | 0 | 0.00 | 1752 | 0.7 |
| openrouter | repair | 95.5 [91.7, 97.6] (n = 200) | 82.0 [76.1, 86.7] (n = 200) | 82.0 [76.1, 86.7] (n = 200) | 0.0 [0.0, 10.2] (n = 34) | 0 | 0 | 0.23 | 2177 | 0.8 |

Per event type (pooled counts): precision = matched / accepted, recall = matched / true.

| Backend | Condition | absence P | absence R | work_increase P | work_increase R | new_activity P | new_activity R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ollama | single_shot | 0.472 | 0.417 | 0.953 | 1.000 | 1.000 | 0.770 |
| ollama | repair | 0.491 | 0.467 | 0.938 | 1.000 | 1.000 | 0.919 |
| openrouter | single_shot | 0.967 | 0.967 | 1.000 | 1.000 | 1.000 | 0.473 |
| openrouter | repair | 0.967 | 0.967 | 1.000 | 1.000 | 1.000 | 0.743 |

Field accuracy on matched events (pooled; absence.return_day is the return-day accuracy).

| Backend | Condition | absence.return_day | work_increase.factor | new_activity.duration | new_activity.crew | new_activity.after | new_activity.before |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ollama | single_shot | 0.520 | 0.590 | 0.965 | 0.982 | 0.737 | 1.000 |
| ollama | repair | 0.464 | 0.590 | 0.971 | 0.926 | 0.721 | 0.912 |
| openrouter | single_shot | 0.845 | 1.000 | 1.000 | 0.886 | 1.000 | 1.000 |
| openrouter | repair | 0.845 | 1.000 | 1.000 | 0.891 | 0.982 | 1.000 |

Repair - single shot, paired by message (percentage points, 95 % cluster bootstrap over instances).

| Backend | Exact | End to end |
| --- | --- | --- |
| ollama | +1.0 [+0.0, +2.5] | +1.0 [+0.0, +2.5] |
| openrouter | +6.5 [+3.5, +10.0] | +6.5 [+3.5, +10.0] |
