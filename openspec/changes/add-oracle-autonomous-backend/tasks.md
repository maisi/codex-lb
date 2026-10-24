## 1. Connection preparation

- [x] 1.1 Add an optional Oracle Thin driver dependency and verify the frozen lockfile and driver imports.
- [x] 1.2 Add the read-only Oracle database CLI check and verify successful, failed, redacted-error and cleanup paths through the CLI.
- [x] 1.3 Add steady-state/update-overlap session budgeting and verify the two-instance 16/24-session example and rejected invalid budgets.
- [x] 1.4 Initially reject unsupported Oracle application startup and schema mutation before connection; verify CLI and startup regression coverage (superseded by verified milestone 5).
- [x] 1.5 Verify the supplied live OCI wallet with native synchronous/asynchronous Thin connections over the operator-selected TP service; inspect service limits, session timezone and package grants read-only without creating application schema.

## 2. Schema groundwork

- [x] 2.1 Preserve Oracle subsecond timestamps and fixed binary hash equality with dialect variants; verify emitted Oracle DDL and unchanged SQLite/PostgreSQL DDL.
- [x] 2.2 Establish generated Oracle numeric identifier handling without changing SQLite/PostgreSQL schemas; verify identity generation contracts.
- [x] 2.3 Record and test the remaining bounded-string, partial-index and empty-string representation blockers; verify the compatibility report identifies them.

## 3. Oracle installation and runtime completion

- [x] 3.1 Implement an Alembic-owned fresh Oracle baseline and cross-process migration serialization; verify upgrade, drift, interrupted-upgrade recovery and schema preservation on real Oracle.
- [x] 3.1.1 Add Oracle DBMS_LOCK migration serialization with a dedicated session, bounded waits and explicit package-privilege errors; verify concurrent migrators, timeout, DDL-commit survival, exception cleanup and process loss on real Oracle.
- [x] 3.2 Port upserts, refresh/file ownership, leader leases, identity locks and account accounting; verify concurrent winners, failure cleanup and settlement ordering on real Oracle.
- [x] 3.2.1 Prepare Oracle file pin ownership with database-time expiry and row-lock serialization; verify concurrent different-account winners, same-owner refresh, expiry takeover, post-lock TTL and rollback cleanup on real Oracle while application startup remains disabled.
- [x] 3.2.2 Prepare Oracle scheduler leader acquisition and renewal; verify concurrent first owners, expiry takeover, non-owner demotion, lock-wait TTL and no expired-lease resurrection on real Oracle.
- [x] 3.2.3 Prepare Oracle token-refresh claims; verify concurrent owners, same-pair re-entry, distinct-token exclusion, exact-owner release, expiry takeover and post-lock database-clock TTL on real Oracle.
- [x] 3.2.4 Bound Oracle query cancellation and connection reclamation under row-lock waits and network loss; resolve the strict expected-failure regression before enabling runtime.
- [x] 3.2.5 Prepare Oracle shared cache invalidation; verify concurrent first insertion, exact version increments, transaction rollback and peer callback delivery on real Oracle.
- [x] 3.2.6 Prepare Oracle encryption-key fingerprint stamping; verify concurrent same/different-key first boots, immutable stored ownership and existing mismatch modes on real Oracle.
- [ ] 3.3 Port timestamp/report functions, schema discovery, retention and empty-string storage; verify product API contracts against SQLite/PostgreSQL equivalents.
- [x] 3.3.1 Initialize every Oracle request/background pool session in UTC and verify naive-UTC defaults and comparisons under a non-UTC client environment; the live OCI probe inherited +02:00 despite a +00:00 database timezone.
- [x] 3.4.1 Run real OCI single-instance application startup, API persistence/accounting, restart and shutdown verification.
- [ ] 3.4.2 Run two-instance failover tests; verify host loss, lease expiry, duplicate-refresh prevention and connection-budget peaks (deferred by operator).

## 4. Reviewable delivery

- [x] 4.1 Document preparation commands, support boundaries, Free-tier limits and HA topology in OpenSpec context and linked published docs; verify examples and documentation links.
- [x] 4.2 Run relevant regression tests, lint/type checks and strict OpenSpec validation; record exact results and remaining live verification in the change context.
- [x] 4.3 Open a draft PR with implemented scope, deferred tasks, validation evidence and a two-hour status report; verify its GitHub URL and head state.

## 5. Single-instance runtime milestone (2026-10-24)

- [x] 5.1 Resolve Oracle string/empty-value and filtered-index representations, preserving round-trip values and uniqueness; verify real database DDL and data operations.
- [x] 5.2 Install a versioned, immutable Oracle Alembic baseline into an isolated schema; verify fresh upgrade, repeat upgrade, drift and interrupted installation handling.
- [x] 5.3 Enable bounded request/background Oracle pools with wallet TLS, per-connection UTC and cancellation/cleanup regression checks.
- [x] 5.4 Port single-instance startup and application repository paths, including settings, accounts, keys, usage/logs, sticky routing and optional bridge paths; preserve SQLite/PostgreSQL contracts.
- [x] 5.5 Verify startup, dashboard/API persistence, account/key operations, stubbed proxy request accounting, restart and shutdown on real Oracle with no changes to existing administrator schema/data.
- [x] 5.6 Enable runtime only after the milestone verification passes; document single-instance scope and remaining HA tasks and update the PR with exact evidence.
