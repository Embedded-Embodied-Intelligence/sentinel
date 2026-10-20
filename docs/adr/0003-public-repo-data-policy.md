# ADR-0003: Public repository, data and secrets policy

- Status: accepted
- Date: 2026-10-20
- WP: WP−1

## Context

The repository must be public (university practice). GitHub is the only backup. Secrets
(Groq key, Claude credentials) must never leak. PSPLIB data has its own source and terms.

## Decision

- Code, configs, docs, small results (tables, figures, CSV) and the LLM cache are committed.
- PSPLIB is downloaded by `scripts/fetch_psplib.py` into `data/` (gitignored).
- Large raw outputs are not committed; they are reproducible from code, configs and seeds.
- Secrets live only in `.env` (gitignored); `.env.example` documents variable names.
- A pre-commit secret scanner (detect-secrets) blocks accidental commits of keys.
- No Git LFS (bandwidth limits on public clones); large artefacts, if ever needed, go to a
  GitHub Release or Zenodo.

## Consequences

Anyone can clone and reproduce. Work not yet pushed has no backup, so WPs end with a push.
