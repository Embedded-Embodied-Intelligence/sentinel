# ADR-0030: A per-sandbox request log in the demo for the remote usability test

- Status: accepted
- Date: 2026-11-03
- WP: WP13

## Context

The usability test runs remotely and unmoderated on the public demo (ADR-0024, ADR-0026): two
or three testers send back clock times per task, and the owner checks them against what the app
recorded. A sandbox's event log has the project, the plan, the check-ins, the recommendations,
the decisions and the simulator's days, and its jobs have their start and end, but nothing shows
when the tester arrived, which pages they opened, or which forms the app refused (422). The demo
must keep storing no address and no form content, and a visitor must not be traceable across
sandboxes.

## Decision

With `request_log = true` (set in `configs/app_demo.toml`; ignored outside the demo) the request
guard writes one row per request of a sandbox to a `requests` table (schema version 2): the time,
the method, the matched route's path template (`/projects/{project_id}/checkin`, never the real
path or its query), the project it names if it is one of the sandbox's own, whether it was an
HTMX request, and the status answered (500 for a crash). Static files, the health check and
requests without a sandbox are not logged. The rows reference the session with `ON DELETE
CASCADE`, so they go with the sandbox after 24 hours. `scripts/usability_logs.py` reads the
database read-only and writes a tester's timeline and task durations without any id.

## Alternatives considered

| Option | Why not |
| --- | --- |
| The server's access log (uvicorn) | Holds client addresses and real paths with ids; not per sandbox; kept outside the 24 h deletion |
| Only the event log and the job table | No start of task 1, no pages opened, no refused forms (the protocol's error count) |
| Log in the browser (JavaScript) | Needs a new endpoint for the data anyway; the pages work without JavaScript beyond HTMX |
| Real paths with ids replaced by hand | The route's template already is that, with no parsing |
| Always on in demo mode | Collects more than any purpose needs once the test is over; the flag turns it off |

## Consequences

One insert per request in the demo, written in a worker thread so the event loop does not wait:
about 19 ms on the server, as long as any insert of the app (an event, a job), nearly all of it
the commit's sync (0.4 ms with `synchronous = OFF`, which the store does not use). The export must
run within 24 hours of a tester's first request, before the sandbox expires. A tester who opens the
demo in two browsers has two sandboxes; the export lists both. Tests cover the logged fields,
the absence of addresses, ids typed into a path, queries and form text, the deletion with the
sandbox, and no log outside the demo or with the flag off.
