## Context

The application uses SQLAlchemy 2.0.52, async request/background engines, and synchronous Alembic migrations. Oracle's native asynchronous driver is available, but runtime SQL and the 289-revision migration history assume SQLite/PostgreSQL. Always Free allows 30 database sessions and 20 GB of storage. The initial spike verified driver and SQL semantics in an owned local Oracle Free container. A subsequent read-only follow-up verified native sync/async TCPS wallet connections to the supplied OCI target over the operator-selected TP service; a later milestone installed the versioned schema and exercised the real single-instance application lifecycle on OCI. HA checks remain pending.

## Goals / Non-Goals

**Goals:** Deliver reviewable, tested Oracle preparation in a draft PR; provide a safe way to validate a future Oracle connection; preserve existing backend behavior; retain the complete two-instance implementation checklist.

**Non-Goals:** Claim production Oracle or HA support on compilation tests alone; modify historical Alembic revisions; automatically migrate an existing SQLite/PostgreSQL database; provision cloud resources.

## Decisions

### Opt-in Thin driver and bounded read-only preflight

Provide an `oracle` extra and `codex-lb-db oracle-check` entry point. Parse SQLAlchemy's native `oracle+oracledb` URL and check native synchronous and asynchronous Thin connections in a bounded subprocess. An explicit preflight queries `SELECT 1 FROM DUAL` and driver-provided server information, but never creates, stamps, alters, or drops application schema. It must release connections on success and failure, avoid printing credentials/wallet secrets, and distinguish connectivity from application readiness.

Use existing pool settings. Show a total budget of `2 * (pool_size + max_overflow) * replicas`, with additional replicas counted explicitly for update overlap. Recommend pool size four and zero overflow for the planned two-instance Free deployment. A SQL session budget is not a throughput guarantee.

### Oracle-specific representations retain existing backend contracts

Add dialect variants only where their mapping is unambiguous: timestamp precision, generated numeric identities, and fixed binary hashes. String bounds, partial index semantics, empty-string encoding, and schema snapshots require explicit decisions and must not be silently approximated. Oracle compatibility tests must inspect emitted SQL and semantic edge cases; a successful SQLAlchemy compilation is insufficient evidence of server acceptance.

### Enable the verified single-instance path

Select the native Thin driver and a separate Oracle migration lineage. Single-instance runtime is enabled after installation and real application/API verification on OCI. Reject alternate drivers, manual schema stamping and legacy SQLite/PostgreSQL Alembic replay before mutation. HA acceptance remains separate.

### Coordinate through the database

Future Oracle runtime support must implement conditional lease ownership, database-clock expiry, refresh claims, file ownership, atomic accounting and migration serialization. It must preserve settlement ordering and task/session ownership. Keep this work explicit in tasks rather than emulating PostgreSQL locks with process-local locks.

## Risks / Trade-offs

- Local Oracle Free verifies transactions and prepared coordination. Live OCI TCPS/wallet connections, app-user package execution, versioned installation and the single-instance application/API lifecycle are verified. Full application failover remains unverified.
- The live OCI session inherited +02:00 despite DBTIMEZONE +00:00. Both Oracle pools now initialize UTC before application use; native tests cover naive timestamps/defaults and non-UTC sessions.
- Native cancellation-first RESET can wait indefinitely. Own and shield native operations through their call timeout before propagating cancellation; the former expected failure now passes, and a single-slot pool recovers while the blocker remains held. Runtime calls allow 15 seconds (native recovery can add 15); migration calls allow 60 seconds because initial Autonomous Free LOB writes exceeded five seconds.
- Oracle treats empty strings as NULL: an Oracle-only reversible codec preserves empty/NULL/sentinel values and rejects oversized identifiers without truncation.
- Oracle DDL commits implicitly: the Alembic-owned immutable baseline verifies surviving objects before resuming interrupted installation.
- Shared Oracle is a common dependency for both application hosts: document the Free-tier recovery limitations and external export requirements.

## Migration Plan

Existing SQLite/PostgreSQL installations require no action. The optional preparation tooling is additive. Full Oracle installation will need a separately verified Alembic baseline, drift checks and single migration owner before any application replica starts. Do not create schema from live ORM metadata and stamp it as a substitute for a migration.


## Single-instance milestone

The single-instance milestone replaces the original preparation-only boundary after fresh OCI installation and actual application/API paths pass. Use an isolated application schema, a separate immutable Oracle Alembic baseline, reversible Oracle-only text encoding and function indexes for conditional uniqueness. The live ADMIN schema is not an application installation target. Native Thin connections must reuse the wallet/TLS validation rules, initialize UTC, and fit both pools in the 30-session budget. HA acceptance tests and claims remain deferred.
