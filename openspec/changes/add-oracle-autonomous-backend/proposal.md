## Why

An operator wants to run codex-lb on Oracle Autonomous Transaction Processing Always Free, initially with one application instance and later with two instances sharing the database. The current SQLite/PostgreSQL implementation cannot safely run on Oracle, and a two-hour implementation spike must make its verified progress and remaining work explicit.

## What Changes

- Add an optional Oracle Thin driver and a read-only database preflight that verifies connectivity and budgets both application pools across replicas, including update overlap.
- Establish Oracle-specific schema representations and regression checks without changing SQLite/PostgreSQL storage contracts.
- Implement and test the first Oracle coordination primitives where the existing repository interfaces permit a narrow change.
- Reject unsupported Oracle application startup and schema mutation until the remaining migration and runtime paths are implemented and verified.
- Record outstanding migration, query, accounting, ownership, and live two-instance validation work in the draft PR rather than claiming production support.

## Capabilities

### New Capabilities

- `oracle-database`: Oracle preparation, read-only connection validation, connection budgeting, and explicit support boundaries.

### Modified Capabilities

None in this initial draft. Existing SQLite/PostgreSQL and multi-replica contracts remain authoritative until the full Oracle port is verified.

## Impact

Python optional dependencies; database CLI and backend selection; Oracle-specific model types and coordination SQL; focused tests and operator documentation. No new mandatory setup, dashboard control, or `CODEX_LB_*` setting is required. Existing installations keep their current database behavior.
