# ADR-0004: Handover cost instead of time–cost crashing

- Status: accepted
- Date: 2026-10-19
- WP: design

## Context

Classical project scheduling shortens activities at linear cost ("crashing"). In software
projects adding people to a late task tends to delay it further (Brooks's law).

## Decision

No crashing operation. Reassigning a paused activity to other workers adds work
`h_j = max(1, ceil(α · e_j))` (spec §3), growing with the context already accumulated.

## Consequences

The model captures the real trade-off of "wait for the person" vs "hand over now".
`α` is a sensitivity parameter, not an empirical constant.
