# ADR-0036: Evidence sources, text extraction and the quote check

- Status: accepted
- Date: 2026-11-13
- WP: WP18

## Context

The v3 interface and the graded presentation show short quotes from studies, laws and standards
next to each design decision. One invented or misquoted sentence would be fatal, so every quote
must be checked by code against the source's own text. Sources are mostly PDFs (arXiv, NBER,
repositories), some web pages and the Official Journal. They must not be committed
(invariant 5), and no runtime dependency may be added. On 2026-11-13 eur-lex.europa.eu
presented a certificate for another host; Harvard DASH answered 429, some sites 403.

## Decision

`scripts/fetch_evidence.py` downloads each open source listed in the registry into
`data/evidence/` (gitignored) with an honest user agent, extracts PDF text with **pdfminer.six
as a development-only dependency** and HTML/XML text with the standard library, and records
SHA-256 digests. A quote is `verified` only if it occurs in that text after a documented
normalisation (NFC, ligatures, curly quotes, line-break hyphenation, white space;
`sentinel.evidence.verify`). EU law comes from the Publications Office (Cellar), which serves the
same Official Journal documents as EUR-Lex; abstracts of paywalled articles come from PubMed.
A source that refuses the fetcher is not worked around: its item stays `summary_only`, or the
owner supplies the PDF (`manual` sources).

## Alternatives considered

| Option | Why not |
| --- | --- |
| pypdf | dropped words in one of four test papers (Bansal et al.): a quote that is there failed |
| poppler `pdftotext` | a system tool, not reproducible through `uv` on both machines |
| PyMuPDF | AGPL licence in an MIT repository |
| Fuzzy matching (edit distance) | would accept a misquote; the check must be exact up to typography |
| Quotes from the research report or reprints | not the source's text; the WP forbids it |
| A browser user agent for 403/429 sites | circumvents the site's decision; not done |

## Consequences

The quote test (`pytest -m data`) is reproducible on any machine after one fetch; a source that
changes upstream is reported by its digest, and its quotes are checked against the new text.
Scanned or badly encoded PDFs (one MPG copy had no spaces) need another open copy. Paywalled
sources keep a summary until the owner adds the PDF. The registry lives in `docs/research/`,
outside the installed package; v3 must ship it with the application.
