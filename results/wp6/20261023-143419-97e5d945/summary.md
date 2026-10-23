# RQ5 event parser — run 20261023-143419-97e5d945

200 messages, backends ollama. Shares in % with 95 % Wilson intervals.

| Backend | Condition | Valid | Exact | End to end | Noise false positives | Leaks | Raw leaks | Rounds | Tokens / msg | Latency / msg (s) |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| ollama | single_shot | 84.5 [78.8, 88.9] (n = 200) | 50.0 [43.1, 56.9] (n = 200) | 50.0 [43.1, 56.9] (n = 200) | 8.8 [3.0, 23.0] (n = 34) | 0 | 0 | 0.00 | 1471 | 6.5 |
| ollama | repair | 97.0 [93.6, 98.6] (n = 200) | 51.0 [44.1, 57.8] (n = 200) | 51.0 [44.1, 57.8] (n = 200) | 8.8 [3.0, 23.0] (n = 34) | 0 | 0 | 0.23 | 1844 | 7.4 |

Per event type (pooled counts): precision = matched / accepted, recall = matched / true.

| Backend | Condition | absence P | absence R | work_increase P | work_increase R | new_activity P | new_activity R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ollama | single_shot | 0.472 | 0.417 | 0.953 | 1.000 | 1.000 | 0.770 |
| ollama | repair | 0.491 | 0.467 | 0.938 | 1.000 | 1.000 | 0.919 |

Field accuracy on matched events (pooled; absence.return_day is the return-day accuracy).

| Backend | Condition | absence.return_day | work_increase.factor | new_activity.duration | new_activity.crew | new_activity.after | new_activity.before |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ollama | single_shot | 0.520 | 0.590 | 0.965 | 0.982 | 0.737 | 1.000 |
| ollama | repair | 0.464 | 0.590 | 0.971 | 0.926 | 0.721 | 0.912 |

Repair - single shot, paired by message (percentage points, 95 % cluster bootstrap over instances).

| Backend | Exact | End to end |
| --- | --- | --- |
| ollama | +1.0 [+0.0, +2.5] | +1.0 [+0.0, +2.5] |
