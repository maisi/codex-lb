## Context

The application uses SQLAlchemy 2.0.52, async request/background engines, and synchronous Alembic migrations. Oracle's native asynchronous driver is available, but runtime SQL and the 289-revision migration history assume SQLite/PostgreSQL. Always Free allows 30 database sessions and 20 GB of storage. The initial spike verified driver and SQL semantics in an owned local Oracle Free container. A subsequent read-only follow-up verified native sync/async TCPS wallet connections to the supplied OCI target over the operator-selected TP service; schema installation and full application checks remain pending.

## Goals / Non-Goals

**Goals:** Deliver reviewable, tested Oracle preparation in a draft PR; provide a safe way to validate a future Oracle connection; preserve existing backend behavior; retain the complete two-instance implementation checklist.

**Non-Goals:** Claim production Oracle or HA support on compilation tests alone; modify historical Alembic revisions; automatically migrate an existing SQLite/PostgreSQL database; provision cloud resources.

## Decisions

### Opt-in Thin driver and bounded read-only preflight

Provide an `oracle` extra and `codex-lb-db oracle-check` entry point. Parse SQLAlchemy's native `oracle+oracledb` URL and check native synchronous and asynchronous Thin connections in a bounded subprocess. An explicit preflight queries `SELECT 1 FROM DUAL` and driver-provided server information, but never creates, stamps, alters, or drops application schema. It must release connections on success and failure, avoid printing credentials/wallet secrets, and distinguish connectivity from application readiness.

Use existing pool settings. Show a total budget of `2 * (pool_size + max_overflow) * replicas`, with additional replicas counted explicitly for update overlap. Recommend pool size four and zero overflow for the planned two-instance Free deployment. A SQL session budget is not a throughput guarantee.

### Oracle-specific representations retain existing backend contracts

Add dialect variants only where their mapping is unambiguous: timestamp precision, generated numeric identities, and fixed binary hashes. String bounds, partial index semantics, empty-string encoding, and schema snapshots require explicit decisions and must not be silently approximated. Oracle compatibility tests must inspect emitted SQL and semantic edge cases; a successful SQLAlchemy compilation is insufficient evidence of server acceptance.

### Fail closed until the complete backend is verified

Detect Oracle before generic PostgreSQL helpers or schema mutation. Incomplete runtime/migration support produces a clear actionable error and points to the read-only preflight. The preparation command remains usable without importing the application engine. No hidden escape hatch enables unsupported production operation.

### Coordinate through the database

Future Oracle runtime support must implement conditional lease ownership, database-clock expiry, refresh claims, file ownership, atomic accounting and migration serialization. It must preserve settlement ordering and task/session ownership. Keep this work explicit in tasks rather than emulating PostgreSQL locks with process-local locks.

## Risks / Trade-offs

- Local Oracle Free verifies transactions and prepared coordination. Live OCI TCPS/wallet connectivity is now verified for the supplied administrator, while app-user package execution, installation and full application failover remain unverified: keep the PR draft.
- The live OCI session inherited +02:00 despite DBTIMEZONE +00:00. Both future Oracle pools need explicit per-connection UTC initialization and naive timestamp/default regression coverage.
- Native cancellation while waiting for a row lock exceeds the observed five-second bound on both frozen SQLAlchemy 2.0.52 and isolated 2.0.55. Keep a strict expected-failure regression and block runtime until cancellation/connection reclamation is bounded.
- Oracle treats empty strings as NULL: design reversible storage encoding before enabling affected request/report paths.
- Oracle DDL commits implicitly: use an Alembic-owned Oracle baseline and test interrupted migrations before supporting installation.
- Shared Oracle is a common dependency for both application hosts: document the Free-tier recovery limitations and external export requirements.

## Migration Plan

Existing SQLite/PostgreSQL installations require no action. The optional preparation tooling is additive. Full Oracle installation will need a separately verified Alembic baseline, drift checks and single migration owner before any application replica starts. Do not create schema from live ORM metadata and stamp it as a substitute for a migration.
