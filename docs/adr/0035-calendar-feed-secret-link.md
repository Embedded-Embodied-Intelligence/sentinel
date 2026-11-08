# ADR-0035: A project's calendar as an iCalendar feed behind a revocable secret link

- Status: accepted
- Date: 2026-11-08
- WP: WP16

## Context

`docs/design/v2-spec.md` §8.9 asks for a calendar a manager subscribes to (Google Calendar,
iCloud): the deadline, task starts and ends, absences as dates only, decision validity dates and
a weekly report reminder (Thursday 17:00 by default, changeable). A calendar fetches the feed by
URL every few hours, without the app's session cookie, so the URL itself must authorise it; in
the demo every visitor is a sandbox session that expires. No new runtime dependency (ADR-0025).

## Decision

The link is `/calendar/{project}/{token}.ics`, where `token` is the first 128 bits of
HMAC-SHA256(app key, `calendar:{project}:{nonce}`) and the per-project `nonce` (random, 144 bits)
is the only thing stored (table `calendars`, schema migration 4, with the reminder's weekday and
time). "Utwórz link" sets a nonce, "Unieważnij link" clears it, a new link replaces it, so every
older URL stops matching at once. The feed path makes no sandbox (it is rate-limited like any
request); it reads the project through the session that owns it and answers 404 for a wrong
token, a revoked link or a project that is gone (its row cascades with the project and with the
sandbox). The text is written with the standard library to RFC 5545: all-day events as `DATE`,
the reminder at a floating local time with `RRULE:FREQ=WEEKLY`, stable `UID`s so updates
replace events, escaped text, lines folded at 75 octets; a dev-only test reads it with
`icalendar`.

Contents: the deadline; for tasks not done, the planned start of those not started and the
expected end; each absence as "Nieobecność: {name}" over its dates; "Decyzja ważna do dziś" on
the validity date of a decision waiting; the weekly reminder. Never a reason for an absence
(the model has none, invariant 7), no costs, no chances. The settings page warns: "Kto ma ten
link, widzi imiona osób i daty nieobecności."

## Alternatives considered

| Option | Why not |
| --- | --- |
| A random token stored as is | a copy of the database would hand out working links |
| A token stored hashed | the page could not show the link again for copying |
| A session-authorised download (.ics file) | no live updates; the user re-imports by hand |
| The `icalendar` package at run time | a new runtime dependency for ~100 lines of text |
| Timed events with a `VTIMEZONE` for Europe/Warsaw | a floating time is valid, simpler, and shown in the calendar's own zone |

## Consequences

- Revocation is immediate and needs no list of old tokens; rotating the app's key revokes all.
- A calendar refreshes on its own schedule (hours), so changes reach it late; the page says so.
- In the demo the link works while the visitor's sandbox lives and then answers 404.
- The validity of a pending decision is computed by its background job; a feed fetched before
  the job finished omits it until the next refresh.
