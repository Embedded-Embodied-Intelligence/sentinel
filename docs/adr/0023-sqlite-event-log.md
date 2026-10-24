# ADR-0023: Projects as an append-only event log in SQLite

- Status: accepted
- Date: 2026-10-24
- WP: WP9a

## Context

A live project changes at check-ins, recommendations and decisions (spec §11); a simulator
project by advancing days. The owner fixed SQLite from the standard library. The results must be
deterministic for a fixed seed and auditable: a manager should see what was reported, what
Sentinel recommended and who approved what. Some steps are expensive (a CP-SAT baseline, a
deliberation with hundreds of rollouts, CP-SAT re-plans on approval) and must not be repeated
to show a project. The demo serves many anonymous visitors on one server.

## Decision

One database file (`sentinel.db`) with sessions, projects, events, jobs and usage counters,
migrated by `PRAGMA user_version`. A project *is* its event log: `created`/`imported`,
`definition`, `baseline`, `checkin`, `recommendation`, `decision` (simulators: `simulator`,
`advance`). An event stores what it resolved to (the baseline's starts, a check-in's starts,
crews, work done and factors, the recommendation's decision record, an action's new plan,
crews, temporary workers and handovers), so replaying the log rebuilds the state without solver
calls or rollouts; a simulator replays its days, which is deterministic for its seed. Events are
never updated (an SQLite trigger refuses it), only deleted with their project. Every query of a
project or job names the session that owns it.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A table per entity (tasks, crews, absences) updated in place | No history; an approval or a check-in correction would overwrite what was reported |
| Events with the inputs only, recomputed on replay | Replay would re-run CP-SAT and rollouts, and a solver or library update could change history |
| Pickled engine states | Opaque, version-fragile, unsafe to load from a file another process could write |
| An ORM (SQLAlchemy) or another database | Not on the dependency list; the schema is five tables |

## Consequences

Rebuilding a live project costs one pass over its events (milliseconds; applying an action uses
the engine's `rehearse`, no solver). A simulator rebuilt after a restart re-simulates its days
(seconds), so the service keeps recent ones in memory. Schema changes need a migration, payload
changes a version check in the replay. Deleting a project or an expired demo sandbox removes its
log for good, which is what the 24-hour demo promises.
