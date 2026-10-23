# Implementation and verification log

## Intended deployment

The operator targets Autonomous Transaction Processing Always Free, initially one application instance and eventually two behind a health-aware load balancer. No OCI test database or wallet has been supplied. Work proceeds against an isolated local Oracle Free container; this verifies SQL/driver semantics and does not establish OCI connectivity or production readiness.

## Verified preparation

- Optional python-oracledb 26.0.1 Thin driver with native sync/async checks against Oracle Free 23.26.3.0.0.
- Read-only connection preflight, an offline schema inventory, credential-safe errors and a bounded preflight worker.
- Both pools counted for steady-state/update overlap: size four, overflow zero, two instances plus one extra gives 16/24 application sessions and six spare under the Free limit.
- Oracle timestamp microseconds and UTC instants, including offset inputs, non-UTC sessions, defaults and RETURNING; RAW(32) invitation hashes and ten generated-ID sequences.
- Exact pre-edit SQLite/PostgreSQL DDL comparison across 68 tables and 92 indexes; fresh SQLite Alembic upgrade/check reports no drift.
- Oracle migration serialization through DBMS_LOCK across independent processes, commits, body failure and process loss. The local test schema was explicitly granted package access; OCI permissions are still unknown.
- Oracle file ownership with a forced simultaneous-first-read race, account isolation, expiry takeover, fresh post-lock TTL and rollback after a non-unique integrity error.
- Oracle token-refresh ownership through the existing coordinator: one concurrent owner pair, same-pair re-entry, distinct-token exclusion, exact-owner release, UTC expiry takeover and full TTL after lock waits.
- Oracle scheduler leadership through the existing LeaderElection API: one concurrent winner, renewal, takeover, release, shutdown renewal, full TTL after a lock wait and no resurrection of an expired lease.

## Local validation

The initial combined regression selection passed **390 tests**, with **11 PostgreSQL-only tests skipped** on the SQLite selection. It covered the new preparation suites plus existing database sessions, migration CLI/history, file API and migration serialization. A further selection of existing leader-lifecycle tests and all Oracle integration suites passed **65 tests** (including the four new Oracle leader cases).

The final Oracle integration selection passed **27 tests** and retained **one strict expected failure** for bounded cancellation. A combined refresh selection passed **60 tests** (five new Oracle ownership cases plus existing unit/integration cases). The schema review additionally includes a real Oracle CLOB empty-bind regression.

Full Ruff/type checks, project architecture/settings/migration-topology checks, strict changed OpenSpec validation and the new capability validation passed. The Oracle workflow is also checked with pinned actionlint 1.7.7; an initial job-level service-port context was corrected to step-level environment configuration with a string port key.

GitHub PR: https://github.com/maisi/codex-lb/pull/43 (draft). Cloud checks refer to their actual head SHA; results must be refreshed after each follow-up commit.

## Remaining production blockers

The full Oracle port is incomplete: no Alembic-owned Oracle installation baseline, interrupted-DDL recovery or live OCI TLS/wallet validation exists yet. The inventory still reports 199 unbounded strings, seven filtered-index definitions and 363 VARCHAR/Text empty-value review entries (569 total). A real Oracle bind/read regression confirms that an empty Python string becomes NULL in a nullable CLOB and fails in a NOT NULL CLOB. These are review items rather than independent task estimates. Additional upserts, bridge/ring ownership, identity/rate-limit locking, reservations/accounting, schema discovery and reports remain to be ported. Bounded query cancellation and connection reclamation are an additional measured blocker: the canceled row-lock test exceeds five seconds on both the frozen SQLAlchemy 2.0.52 / oracledb 26.0.1 stack and an isolated SQLAlchemy 2.0.55 check. Documented native cancel, call-timeout and out-of-band settings, and an isolated oracledb 3.4.2 check did not establish bounded cancellation; no workaround or dependency change was adopted. The strict expected-failure marker accepts only this dedicated deadline exception; unrelated assertion or fixture cleanup failures still fail the test.

Application startup and schema mutation therefore remain explicitly disabled for every Oracle URL. Do not remove that guard on the strength of connection or prepared-coordination tests. The change must remain active until the full task list and single-/two-instance product checks pass.
