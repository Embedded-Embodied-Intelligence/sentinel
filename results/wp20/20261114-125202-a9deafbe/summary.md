# RQ6 — editing reports for audiences — run 20261114-125202-a9deafbe

30 reports (30 synthetic, generated from templates; 0 added by hand), 964 facts; audiences edit, board, finance, team. Shares and rates with 95 % cluster-bootstrap intervals over reports (2000 resamples). A changed fact is the dangerous error; an omitted fact is reported, not an error. A model error (the backend could not answer, or its answer violates the schema) is its own measure, in % of all edits; the fact measures are over the successful edits.

## Model errors

| Backend | Condition | Edits | Model errors | Successful edits | Kinds |
| --- | --- | --- | --- | --- | --- |
| ollama | plain | 120 | 0.0 [0.0, 0.0] | 120 | - |
| ollama | self_report | 120 | 0.8 [0.0, 2.5] | 119 | cache_miss: 1 |
| openrouter | plain | 120 | 0.0 [0.0, 0.0] | 120 | - |
| openrouter | self_report | 120 | 0.0 [0.0, 0.0] | 120 | - |

## Facts in the edited versions (the application's prompt)

Condition plain

| Backend | Audience | Edits | Model errors | Successful edits | With a changed fact | Changed per 100 facts | With a new fact | New per version | Omitted per 100 facts | Length ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ollama | edit | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0.0 [0.0, 0.0] | 0.95 [0.94, 0.96] |
| ollama | board | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0.9 [0.2, 1.9] | 0.93 [0.91, 0.96] |
| ollama | finance | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 15.2 [11.2, 19.8] | 0.70 [0.66, 0.74] |
| ollama | team | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 8.3 [5.0, 11.6] | 0.77 [0.72, 0.82] |
| ollama | all | 120 | 0.0 [0.0, 0.0] | 120 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 6.1 [4.8, 7.6] | 0.84 [0.82, 0.85] |
| openrouter | edit | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 6.7 [0.0, 16.7] | 0.17 [0.00, 0.43] | 0.2 [0.0, 0.5] | 0.82 [0.82, 0.83] |
| openrouter | board | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 6.7 [0.0, 16.7] | 0.17 [0.00, 0.43] | 7.2 [6.6, 7.8] | 0.70 [0.68, 0.72] |
| openrouter | finance | 30 | 0.0 [0.0, 0.0] | 30 | 3.3 [0.0, 10.0] | 0.1 [0.0, 0.3] | 3.3 [0.0, 10.0] | 0.03 [0.00, 0.10] | 7.9 [6.6, 9.7] | 0.66 [0.64, 0.68] |
| openrouter | team | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 10.0 [0.0, 20.1] | 0.27 [0.00, 0.57] | 8.8 [7.3, 10.8] | 0.66 [0.64, 0.68] |
| openrouter | all | 120 | 0.0 [0.0, 0.0] | 120 | 0.8 [0.0, 2.5] | 0.0 [0.0, 0.1] | 6.7 [1.7, 13.3] | 0.16 [0.03, 0.34] | 6.0 [5.4, 6.8] | 0.71 [0.70, 0.72] |

## Facts when the model also lists its changes

Condition self_report

| Backend | Audience | Edits | Model errors | Successful edits | With a changed fact | Changed per 100 facts | With a new fact | New per version | Omitted per 100 facts | Length ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ollama | edit | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0.0 [0.0, 0.0] | 0.97 [0.96, 0.98] |
| ollama | board | 30 | 3.3 [0.0, 10.0] | 29 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 3.4 [0.0, 10.7] | 0.03 [0.00, 0.11] | 3.8 [2.5, 5.1] | 0.92 [0.89, 0.95] |
| ollama | finance | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 13.3 [9.7, 16.8] | 0.87 [0.82, 0.91] |
| ollama | team | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 10.2 [7.6, 13.1] | 0.93 [0.85, 1.04] |
| ollama | all | 120 | 0.8 [0.0, 2.5] | 119 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.8 [0.0, 2.5] | 0.01 [0.00, 0.03] | 6.8 [5.7, 8.0] | 0.92 [0.90, 0.96] |
| openrouter | edit | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 6.7 [0.0, 16.7] | 0.17 [0.00, 0.43] | 0.2 [0.0, 0.5] | 0.82 [0.81, 0.83] |
| openrouter | board | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 6.7 [0.0, 16.7] | 0.17 [0.00, 0.43] | 8.1 [7.2, 9.0] | 0.71 [0.68, 0.73] |
| openrouter | finance | 30 | 0.0 [0.0, 0.0] | 30 | 3.3 [0.0, 10.0] | 0.1 [0.0, 0.3] | 13.3 [3.3, 26.7] | 0.23 [0.03, 0.50] | 8.2 [7.1, 9.6] | 0.63 [0.62, 0.65] |
| openrouter | team | 30 | 0.0 [0.0, 0.0] | 30 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 10.0 [0.0, 23.3] | 0.27 [0.00, 0.60] | 9.9 [8.0, 12.3] | 0.62 [0.59, 0.64] |
| openrouter | all | 120 | 0.0 [0.0, 0.0] | 120 | 0.8 [0.0, 2.5] | 0.0 [0.0, 0.1] | 9.2 [1.7, 18.3] | 0.21 [0.03, 0.45] | 6.6 [5.9, 7.4] | 0.70 [0.69, 0.70] |

## The model's own list of changes against the code diff

Condition self_report

| Backend | Audience | Successful edits | Diff changes per version | Listed per version | Diff changes listed | Listed not in the diff | Changed facts listed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ollama | edit | 30 | 1.13 [0.93, 1.37] | 7.07 [5.37, 8.70] | 73.5 [55.3, 89.7] | 87.7 [81.2, 92.1] | - |
| ollama | board | 29 | 6.34 [5.26, 7.41] | 8.31 [6.30, 10.54] | 48.9 [36.6, 60.4] | 54.4 [41.7, 66.8] | - |
| ollama | finance | 30 | 4.30 [3.37, 5.37] | 5.97 [4.73, 7.47] | 67.4 [54.6, 82.6] | 43.6 [35.0, 52.1] | - |
| ollama | team | 30 | 10.73 [9.17, 12.20] | 6.03 [4.50, 7.77] | 63.7 [52.7, 74.0] | 26.5 [18.6, 34.6] | - |
| ollama | all | 119 | 5.62 [5.08, 6.10] | 6.83 [5.98, 7.75] | 60.8 [54.2, 66.8] | 54.5 [48.3, 60.4] | - |
| openrouter | edit | 30 | 11.20 [10.17, 12.40] | 6.50 [5.47, 7.60] | 84.8 [79.0, 90.0] | 16.9 [9.8, 23.6] | - |
| openrouter | board | 30 | 14.30 [13.23, 15.37] | 3.90 [2.63, 5.27] | 89.5 [82.7, 95.3] | 17.1 [10.5, 25.0] | - |
| openrouter | finance | 30 | 21.43 [19.63, 23.13] | 4.23 [2.97, 5.87] | 91.6 [85.4, 96.2] | 11.8 [6.5, 17.6] | 100.0 [100.0, 100.0] |
| openrouter | team | 30 | 13.93 [12.23, 15.50] | 2.27 [1.13, 3.83] | 97.8 [95.6, 99.5] | 5.9 [0.0, 11.1] | - |
| openrouter | all | 120 | 15.22 [14.32, 16.07] | 4.22 [3.68, 4.86] | 91.3 [88.4, 93.9] | 14.2 [11.4, 17.2] | 100.0 [100.0, 100.0] |

Tokens: 839171 in 480 edits (1 model errors).
