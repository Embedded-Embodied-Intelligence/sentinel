# ADR-0024: Anonymous sandboxes, signed cookies and CSRF tokens for the public demo

- Status: accepted
- Date: 2026-10-24
- WP: WP9a

## Context

The course demo runs `sentinel ui --demo` on the owner's server behind Tailscale Funnel, a
public HTTPS URL. Visitors do not register. The server has 4 cores; a deliberation takes about a
second and a simulator run up to a minute; LLM calls cost quota. No visitor may see another's
data, the server's settings or files, and a hostile page must not act in a visitor's name. The
dependency list allows no session or security library.

## Decision

Every visitor gets an anonymous sandbox: a session row created on the first API request, its id
in an HttpOnly, SameSite=Lax cookie signed with HMAC-SHA256 under a server key kept in the data
directory (mode 0600). Every query of a project or a job names the session (the store refuses
others, and a foreign id answers 404 like a missing one). State-changing requests need the
session's CSRF token, an HMAC of the session id, in the `X-CSRF-Token` header (double submit:
also a readable cookie and in `/api/session`); a request without a valid session is refused, not
given a sandbox. Limits come from `configs/app_demo.toml`: projects per session, tasks per
project, simulator days per advance, concurrent jobs per session, requests per minute per client
address (token bucket; behind the funnel the first `X-Forwarded-For` address), upload size and a
server-wide daily cap of LLM requests. Sandboxes are deleted 24 h after creation with all their
projects, events and jobs. In demo mode the LLM settings endpoints and the API docs do not
exist. Each sandbox starts with a copy of a showcase project computed once per server.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Accounts with passwords | A demo for a course; storing credentials adds risk and friction |
| Starlette's SessionMiddleware | Needs `itsdangerous`, not on the dependency list; the session data live in SQLite anyway |
| CSRF token in a form field | WP9b sends HTMX requests; a header covers forms and fetches alike |
| One shared demo project | Visitors would see and change each other's check-ins and decisions |
| Rate limits in a reverse proxy | The funnel forwards to the app directly; one process holds the buckets |

## Consequences

A visitor who clears cookies starts a new sandbox; the old one expires. The limits bound the
CPU a visitor can take (one job at a time, at most 60 simulated days per request), not the number
of visitors; the funnel's own limits and the per-address rate cap that. Tests cover isolation
(another session's project, job, export and events answer 404), forged cookies, CSRF, the limits
and the expiry.
