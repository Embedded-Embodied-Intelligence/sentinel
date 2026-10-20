# wp1_rq2: run 20261020-105318-3ba2e943

Generated from `results.csv` by `sentinel.experiments.rcpsp_summary`; do not edit.
dev_ref = 100 (C - C_ref) / C_ref and dev_lb0 = 100 (C - LB0) / LB0 in % (spec section
1.5), averaged over the instances with a schedule; matches: C = C_ref; below: C < C_ref.

## J30 (reference: optimum, `opt`)

| Method | n | with schedule | mean dev_ref % | matches | below ref | mean dev_lb0 % | mean runtime s | max runtime s | statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SGS-LFT | 480 | 480 | 5.58 | 240 (50.0%) | 0 | 20.81 | 0.0003 | 0.0043 | FEASIBLE 480 |
| SGS-LST | 480 | 480 | 4.92 | 246 (51.2%) | 0 | 19.95 | 0.0003 | 0.0044 | FEASIBLE 480 |
| SGS-MTS | 480 | 480 | 6.56 | 213 (44.4%) | 0 | 21.84 | 0.0002 | 0.0043 | FEASIBLE 480 |
| SGS-GRPW | 480 | 480 | 10.31 | 182 (37.9%) | 0 | 26.26 | 0.0003 | 0.0064 | FEASIBLE 480 |
| RBRS-1000 | 480 | 480 | 0.82 | 370 (77.1%) | 0 | 14.57 | 0.0865 | 0.2423 | FEASIBLE 480 |
| CP-SAT 1 s | 480 | 480 | 0.09 | 470 (97.9%) | 0 | 13.53 | 0.0835 | 1.0033 | FEASIBLE 18, OPTIMAL 462 |
| CP-SAT 10 s | 480 | 480 | 0.01 | 477 (99.4%) | 0 | 13.39 | 0.2968 | 10.0480 | FEASIBLE 6, OPTIMAL 474 |

## J60 (reference: best known, `hrs`)

| Method | n | with schedule | mean dev_ref % | matches | below ref | mean dev_lb0 % | mean runtime s | max runtime s | statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SGS-LFT | 480 | 480 | 5.73 | 272 (56.7%) | 0 | 18.13 | 0.0005 | 0.0053 | FEASIBLE 480 |
| SGS-LST | 480 | 480 | 5.20 | 281 (58.5%) | 0 | 17.45 | 0.0005 | 0.0049 | FEASIBLE 480 |
| SGS-MTS | 480 | 480 | 6.66 | 232 (48.3%) | 0 | 18.99 | 0.0004 | 0.0034 | FEASIBLE 480 |
| SGS-GRPW | 480 | 480 | 12.80 | 159 (33.1%) | 0 | 26.02 | 0.0005 | 0.0045 | FEASIBLE 480 |
| RBRS-1000 | 480 | 480 | 2.56 | 328 (68.3%) | 0 | 13.99 | 0.1390 | 0.4967 | FEASIBLE 480 |
| CP-SAT 1 s | 480 | 480 | 1.38 | 394 (82.1%) | 0 | 12.51 | 0.2225 | 1.0151 | FEASIBLE 90, OPTIMAL 390 |
| CP-SAT 10 s | 480 | 480 | 0.85 | 417 (86.9%) | 0 | 11.73 | 1.7440 | 10.0754 | FEASIBLE 75, OPTIMAL 405 |
