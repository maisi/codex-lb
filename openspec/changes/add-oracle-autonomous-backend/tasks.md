## 1. Connection preparation

- [x] 1.1 Add an optional Oracle Thin driver dependency and verify the frozen lockfile and driver imports.
- [x] 1.2 Add the read-only Oracle database CLI check and verify successful, failed, redacted-error and cleanup paths through the CLI.
- [x] 1.3 Add steady-state/update-overlap session budgeting and verify the two-instance 16/24-session example and rejected invalid budgets.
- [x] 1.4 Reject unsupported Oracle application startup and schema mutation before connection; verify CLI and startup regression coverage.

## 2. Schema groundwork

- [x] 2.1 Preserve Oracle subsecond timestamps and fixed binary hash equality with dialect variants; verify emitted Oracle DDL and unchanged SQLite/PostgreSQL DDL.
- [x] 2.2 Establish generated Oracle numeric identifier handling without changing SQLite/PostgreSQL schemas; verify identity generation contracts.
- [x] 2.3 Record and test the remaining bounded-string, partial-index and empty-string representation blockers; verify the compatibility report identifies them.

## 3. Oracle installation and runtime completion

- [ ] 3.1 Implement an Alembic-owned fresh Oracle baseline and cross-process migration serialization; verify upgrade, drift, interrupted-upgrade recovery and schema preservation on real Oracle.
- [x] 3.1.1 Add Oracle DBMS_LOCK migration serialization with a dedicated session, bounded waits and explicit package-privilege errors; verify concurrent migrators, timeout, DDL-commit survival, exception cleanup and process loss on real Oracle.
- [ ] 3.2 Port upserts, refresh/file ownership, leader leases, identity locks and account accounting; verify concurrent winners, failure cleanup and settlement ordering on real Oracle.
- [x] 3.2.1 Prepare Oracle file pin ownership with database-time expiry and row-lock serialization; verify concurrent different-account winners, same-owner refresh, expiry takeover, post-lock TTL and rollback cleanup on real Oracle while application startup remains disabled.
- [ ] 3.3 Port timestamp/report functions, schema discovery, retention and empty-string storage; verify product API contracts against SQLite/PostgreSQL equivalents.
- [ ] 3.4 Run real Oracle single-instance API smoke and two-instance failover tests; verify host loss, lease expiry, duplicate-refresh prevention and connection-budget peaks.

## 4. Reviewable delivery

- [x] 4.1 Document preparation commands, support boundaries, Free-tier limits and HA topology in OpenSpec context and linked published docs; verify examples and documentation links.
- [ ] 4.2 Run relevant regression tests, lint/type checks and strict OpenSpec validation; record exact results and remaining live verification in the change context.
- [ ] 4.3 Open a draft PR with implemented scope, deferred tasks, validation evidence and a two-hour status report; verify its GitHub URL and head state.
