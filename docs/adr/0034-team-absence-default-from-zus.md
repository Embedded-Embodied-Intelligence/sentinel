# ADR-0034: One team-wide absence rate from ZUS's sickness-absence statistics

- Status: accepted
- Date: 2026-11-07
- WP: WP15

## Context

The forecast needs the daily absence probability `λ_A` per person (spec §2.2, §11.2). The first
interface asks for a "team" preset (calm 0.005, usual 0.01, turbulent 0.02, with `E[L] = 3`
working days). The v2 design (`docs/design/v2-spec.md`, §2) drops the question: how often a
person is away is unknowable for a novice, health-adjacent (GDPR Art. 9) and invites judging
people. The v2 wizard uses one value for the whole team from public Polish statistics instead.

Source: ZUS (Zakład Ubezpieczeń Społecznych), *Absencja chorobowa w 2025 roku*, Warszawa 2026
(https://www.zus.pl/documents/10182/39590/Raport+Absencja+chorobowa+w+2025+roku.pdf), and its
summary "Coraz częstsze i dłuższe zwolnienia lekarskie" (zus.pl, 28 April 2026): 290.5 million
days of sickness absence in 2025, 254.5 million of them of people insured in ZUS, 27.5 million
certificates of 11 days on average, and **14.76 days of absence per insured person** (14.65 in
2024). The days are those of medical certificates (own illness and care of a family member).

## Decision

A share of `s = 14.76 / 365 = 4.0 %` of days absent, with the model's usual absence length
`E[L] = 3` working days kept, gives `λ_A = s / (E[L] (1 − s)) = 0.014` per person and working
day (spec §8: the share is `E[L] / (1/λ_A + E[L])`). A project created by the v2 wizard stores
`advanced.lambda_a = 0.014`; the wizard says "about 4 % of working days absent, for everyone
alike" and asks nothing about individuals. The other rates keep their usual values.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Ask how often each person is away | unknowable, health-adjacent (GDPR Art. 9), a per-person judgement (AI Act Annex III 4) |
| Keep the "usual" preset (3.2 %) | not grounded in any statistic; Polish data say about 4 % |
| `E[L]` from the certificates (11 calendar days ≈ 8 working days) | short absences without a certificate (1–2 days, leave on demand) are not in ZUS's data, so certificates overstate the usual length; longer, rarer absences would also change every forecast's shape beyond what the data support |
| GUS's absence rates per sector | the project's sector is unknown; one national figure is simpler to explain |

## Consequences

The share counts certificates only, so it is a floor for all absences (holidays are planned and
not in it). The value and its source are shown in the wizard and can be changed in a project's
advanced settings, as every rate can (spec §11.2). Research runs are unchanged. The figure should
be refreshed when ZUS publishes the 2026 report.
