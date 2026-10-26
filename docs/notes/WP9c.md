# WP9c notes — one comparison, threats, names, packaging, deployment and usability

**Purpose.** The architect's review of the WP9b screens found four things that confuse a
manager; spec v2.0.2 (§11) answers them, and the application is then packaged for a company
server, deployed as the public course demo, documented for users and prepared for a usability
test with real people.

**One comparison (§11.5).** The decision is unchanged: Sentinel's deliberation with racing
(§6). After it, the candidates shown — the choice, at most five alternatives (the runner-up,
those racing kept, the rest by `min(p, θ_D)` and `T`) and always NOOP — are evaluated on the
sampled worlds of the overview's forecast of the same day: the same seed
`derive_seed(project seed, "forecast", t)`, the same rollout layout (ADR-0009), `N = 200`.
NoReaction rollouts are NOOP's rollouts, so "no change" is the overview's chance exactly (the
showcase: 39 % on both pages; before, 52 % from 25 racing rollouts against 39 %). After an
automatic action the overview shows the action's own figures, since applying it at step 3 and
re-forecasting from the changed plan run the same worlds (0.615 = 0.615 on the test project).
The comparison is stored with the recommendation (no rollout on replay) and costs about 0.3 s
on the showcase (6 candidates × 200 rollouts, the approvals re-planned on the shared plan
cache). The comparison may rank an alternative above the choice; the decision stands and the
page explains its deciding component.

**Threats (§11.4).** A task's share is the fraction of the completed late rollouts (`C > D`)
whose critical chain (tight links back from the sink) holds it. Structural tasks — on every
source–sink path of the required tasks (optional and dropped tasks are not on these paths) —
zero-duration tasks and tasks already done are left out. Showcase: the first task, the
performance tests and the launch are structural; "Integration tests", "Product catalogue API"
and "Payment integration" decide the deadline in 7, 7 and 6 of 10 of the 122 late futures.
With the optional gift cards counted as a path, only the first task would be structural and the
launch would again head the list, "9 of 10" (spec question).

**Wording and names (§11.2, §11.6, §11.7).** Costs read "27 z 84 jednostek kosztu (osobodni)",
changes "+2 jedn., +2 % budżetu"; the meaning "(osobodni)" appears while every daily cost is 1.
The example projects are named in the user's language from `app/vocabulary/<lang>.toml`; the
simulator draws names with the research narrator's algorithm and seeds (WP6a) from the
language's words, so the English names are the studies' and the Polish ones their item-by-item
translations ("Implement payment API" ↔ "Implementacja API płatności").

**Deployment (ADR-0026).** A two-stage uv image on `python:3.12-slim` (non-root, `/data`
volume, health check), compose with an optional Ollama profile, and the demo behind Tailscale
Funnel. Behind the funnel every request arrives from 127.0.0.1, so the per-visitor limits read
`X-Forwarded-For`, trusted only from that peer and taking the last hop the proxy added; a
remote client cannot choose its address.

**Usability (protocol-pl.md).** A 20-minute moderated think-aloud test, 3–5 participants
without training, five tasks with success criteria and limits, SUS (Brooke 1996) in Polish.
A scripted run of the same tasks gives the floor of clicks, fields and seconds (task 1: 9 clicks
and 4 fields; the simulator task 30 s of computation).

**References.** Bertsekas, Tsitsiklis & Wu 1997 (rollouts); Brooke 1996 (SUS); Nielsen &
Landauer 1993, Nielsen 1994 (problem discovery, severity); Ericsson & Simon 1993 (think-aloud);
Sauro & Lewis 2016 (SUS benchmarks).
