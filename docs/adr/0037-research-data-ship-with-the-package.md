# ADR-0037: The research data ship inside the package

- Status: accepted
- Date: 2026-11-13
- WP: WP19

## Context

The v3 interface ("Dowód", Mapa granic, Źródła, Uprawnienia AI, Ludzie) reads the evidence
registry, the decision catalogue and the boundary map. WP18 kept them under `docs/research/`,
which is outside the installed package: the wheel and the Docker image (which installs the
project non-editable from `src/`) did not carry them. The build backend `uv_build` packs only
what lies inside the module directory and cannot map a file from elsewhere into the wheel. The
catalogue was a Markdown table with English sentences only.

## Decision

The data move into `src/sentinel/evidence/data/` (`registry.json`, `boundary-map.json`, a new
`decisions.json`, and in WP20 the survey summary) and are loaded from the package's own
directory; `docs/research/` keeps the Markdown documents that describe them, and a test checks
that the table of `decisions.md` equals `decisions.json`.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep `docs/research/` and copy the files into the package before a build | Two copies that can drift; every build path (wheel, zip, image) would need the copy step |
| Symbolic links from the package to `docs/research/` | Not followed reliably by every build and archive tool, and break on checkouts without links |
| A build hook that maps the files into the wheel | `uv_build` has no such hook; switching the backend for three files is out of scope |
| Parse `decisions.md` at run time and ship the Markdown | A table cell cannot hold the interface's Polish and English sentences readably |

## Consequences

- One copy of each file; the wheel, the release zip (`git archive` of the tree) and the image
  carry them, and a slow test builds the wheel and loads the data from the extracted package.
- `scripts/fetch_evidence.py --update-registry` writes into the package's registry; the
  detect-secrets exclusion follows the new path.
- WP18's documents and report name the old paths; they describe the state of that WP.
