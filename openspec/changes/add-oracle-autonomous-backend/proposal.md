## Why

An operator wants to run codex-lb on Oracle Autonomous Transaction Processing Always Free, initially with one application instance and later with two instances sharing the database. The original two-hour preparation spike is now extended to verified single-instance operation, with multi-instance HA explicitly deferred.

## Current milestone

The operator now requests verified operation of one codex-lb instance against Oracle Autonomous TP. Implement fresh installation into an isolated application schema and verify normal startup, dashboard/API persistence and shutdown. Multi-instance HA remains explicitly deferred. Existing administrator/application data must be preserved.

## What Changes

- Add an optional Oracle Thin driver and a read-only database preflight that verifies connectivity and budgets both application pools across replicas, including update overlap.
- Establish Oracle-specific schema representations and regression checks without changing SQLite/PostgreSQL storage contracts.
- Implement and test the first Oracle coordination primitives where the existing repository interfaces permit a narrow change.
- Enable the verified single-instance Thin runtime with bounded UTC pools and a separate immutable Oracle baseline; reject manual stamping and legacy migration replay.
- Record outstanding migration, query, accounting, ownership, and live two-instance validation work in the draft PR rather than claiming production support.

## Capabilities

### New Capabilities

- `oracle-database`: Oracle preparation, read-only connection validation, connection budgeting, and explicit support boundaries.

### Modified Capabilities

Existing SQLite/PostgreSQL and multi-replica contracts remain authoritative. The new Oracle capability specifies the isolated single-instance milestone and leaves HA acceptance deferred.

## Impact

Python optional dependencies; database CLI and backend selection; Oracle-specific model types and coordination SQL; focused tests and operator documentation. No new mandatory setup, dashboard control, or `CODEX_LB_*` setting is required. Existing installations keep their current database behavior.
