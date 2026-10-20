# WP0 notes — instance model, PSPLIB data, critical-path bounds

**Instance model (§1, §1.1).** PSPLIB single-mode files are parsed with `psplib` 0.4.0 into a
frozen pydantic `ProjectInstance`; file job `i` becomes activity `i − 1` (source 0, sink `n+1`).
Each renewable resource is a role `R1..R4` whose capacity `R_k` is split into workers
`w = (k, i)`, `i = 0..R_k − 1`, so one person's absence can be modelled later. Construction
enforces positional ids, dummies with `p = r = 0`, no predecessor of 0 and no successor of `n+1`,
`0 ≤ r_jk ≤ R_k`, known unique successors, acyclicity (Kahn 1962, smallest ready id first, which
also fixes a deterministic topological order), reachability (in a DAG with 0 as the only source
and `n+1` as the only sink every activity lies on a 0→`n+1` path) and `R_k` = workers of role `k`.

**Feasibility and bounds (§1.3, §1.4).** `validate_schedule` reports a length mismatch,
`S_0 ≠ 0`, negative starts, precedence violations and resource overloads per (role, day), the
latter from an event sweep over the days where usage changes; `C = S_{n+1}`. CPM (Kelley &
Walker 1959): `ES` by a forward pass and `LB0 = ES_{n+1}`; `LF` by a backward pass from horizon
`T` (default LB0; a smaller `T` gives negative slack); `LS = LF − p`.

**Data.** Downloaded 2026-10-20 from https://www.om-db.wi.tum.de/psplib (Kolisch & Sprecher
1997): flat zips of 480 files `j{n}{Par}_{Inst}.sm` (Par 1–48, Inst 1–10); j30 458,761 B, j60
657,002 B; content hashes j30 `b77624e1…`, j60 `8d9894ce…` (full values in `MANIFEST.json`).
Real durations are 1–10, capacities 3–63 (J30) and 7–94 (J60); activity order is topological.

**Solution-file format.** ASCII: a free-text header, then one line per instance.

| File | Header | Data line | Entries |
| --- | --- | --- | --- |
| `j30_opt.sm` | 20 lines: author and computer metadata (Demeulemeester & Herroelen, June 1995), `===`, `Paramter Instance Makespan CPU-Time[sec.]`, `---` | `1 1 43 0.30` (Par, Inst, optimum, CPU s) | 480 |
| `j30_hrs.sm`, `j60_hrs.sm` | 4 lines: `solutionlist data/j30hrs.sm`, `===`, `Par Inst Makespan Date Author`, `===` | `1 1 77 Tue Apr 2 16:26:00 1996 R. Kolisch / A. Drexl` (best known) | 480 each |
| `j60_lb.sm` | 19 lines: prose (bounds by Brucker & Knust 1998, Heilmann & Schwindt 1997, Klein & Scholl 1997), `===`, `Par Inst LB Author LB`, `===` | `1 4 91 Klein & Scholl Brucker & Knust`; author may be empty | 410 (Par 1–41) |

The parser treats a line starting with three integers `Par Inst Value` as data (the value may
end with `*`, the LB = UB marker announced by the `j60_lb` header but absent from the file); any
other line starting with two integers is an error. Keys look like `j30/j301_1`.

**Reference facts.** J30: `hrs = opt` on all 480; `opt = LB0` on 216 (45%). J60: `lb ≥ LB0`
everywhere; `hrs = lb` (proven optimal) on 382 of 410; Par 42–48 (70 instances) have no `lb`, 46
of them `hrs = LB0`. Hence `opt` (J30) and `hrs` plus `dev_lb0` (J60) as references (§1.5).

**References.** Kolisch & Sprecher 1997; Kelley & Walker 1959 (CPM); Kahn 1962 (CACM 5(11));
Demeulemeester & Herroelen 1997 (J30 optima, Management Science 43(11)); Kolisch & Hartmann 2006.
