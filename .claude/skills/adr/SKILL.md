---
name: adr
description: Record an architecture decision as docs/adr/NNNN-title.md. Use when making a design choice not dictated by docs/spec (new dependency, data format, algorithm variant, interface shape, trade-off between alternatives).
---

# Architecture Decision Record

1. Find the next number: `ls docs/adr/` and take the highest `NNNN` + 1.
2. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-kebab-case-title.md`.
3. Fill it in, at most ~40 lines: Context (facts), Decision (one or two sentences),
   Alternatives considered (table), Consequences.
4. Status `accepted` for decisions within the WP's scope; `proposed` if it changes the spec
   or another ADR (then also raise it under "Spec questions" in the WP report).
5. Mention the ADR in the WP report under "Decisions".

Do not write ADRs for trivial choices (variable names, formatting). Write them when a future
reader (or a paper reviewer) would ask "why was it done this way?".
