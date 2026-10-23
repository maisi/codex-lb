# Implementation and verification log

## Intended deployment

The operator targets Autonomous Transaction Processing Always Free, initially one application instance and eventually two behind a health-aware load balancer. The initial spike used an isolated local Oracle Free container. The operator subsequently supplied a live OCI wallet and credentials and selected the TP service. Native sync/async connectivity now works against that target; application installation and production readiness remain unverified.

## Verified preparation

- Optional python-oracledb 26.0.1 Thin driver with native sync/async checks against Oracle Free 23.26.3.0.0.
- Read-only connection preflight, an offline schema inventory, credential-safe errors and a bounded preflight worker. A silent local TCP endpoint proves that the real native connection is closed when the CLI deadline kills its worker.
- Both pools counted for steady-state/update overlap: size four, overflow zero, two instances plus one extra gives 16/24 application sessions and six spare under the Free limit.
- Oracle timestamp microseconds and UTC instants, including offset inputs, non-UTC sessions, defaults and RETURNING; RAW(32) invitation hashes and ten generated-ID sequences.
- Exact pre-edit SQLite/PostgreSQL DDL comparison across 68 tables and 92 indexes; fresh SQLite Alembic upgrade/check reports no drift.
- Oracle migration serialization through DBMS_LOCK across independent processes, commits, body failure and process loss. The local test schema was explicitly granted package access. A later live catalog probe confirmed an administrator grant on OCI, while the app-user grant and actual OCI lock operation remain unverified.
- Oracle file ownership with a forced simultaneous-first-read race, account isolation, expiry takeover, fresh post-lock TTL and rollback after a non-unique integrity error.
- Oracle token-refresh ownership through the existing coordinator: one concurrent owner pair, same-pair re-entry, distinct-token exclusion, exact-owner release, UTC expiry takeover and full TTL after row-lock waits or a competing first insert that rolls back. Oracle lock-wait tests release their owned blockers before joining canceled tasks, including on assertion failure.
- Oracle shared cache version increments and peer callbacks, including simultaneous first insert, rollback-before-retry and a lost commit acknowledgement. Five native Oracle cases pass alongside 25 existing cache regression cases.
- Oracle startup key fingerprint agreement, including concurrent same-key and divergent-key first boots, immutable canonical key and enforce/warn/off modes. Three native Oracle cases pass alongside 24 existing startup/replica regression cases.
- Oracle scheduler leadership through the existing LeaderElection API: one concurrent winner, renewal, takeover, release, shutdown renewal, full TTL after a lock wait and no resurrection of an expired lease.

## Local validation

The initial combined regression selection passed **390 tests**, with **11 PostgreSQL-only tests skipped** on the SQLite selection. It covered the new preparation suites plus existing database sessions, migration CLI/history, file API and migration serialization. A further selection of existing leader-lifecycle tests and all Oracle integration suites passed **65 tests** (including the four new Oracle leader cases).

The final Oracle integration selection passed **37 tests** and retained **one strict expected failure** for bounded cancellation. A combined refresh selection passed **60 tests** (five new Oracle ownership cases plus existing unit/integration cases). The schema review additionally includes a real Oracle CLOB empty-bind regression.

Full Ruff/type checks, project architecture/settings/migration-topology checks, strict changed OpenSpec validation and the new capability validation passed. The Oracle workflow is also checked with pinned actionlint 1.7.7; an initial job-level service-port context was corrected to step-level environment configuration with a string port key.

GitHub PR: https://github.com/maisi/codex-lb/pull/43 (draft). Cloud checks refer to their actual head SHA; results must be refreshed after each follow-up commit.

## Live OCI follow-up: 2026-10-24 (Europe/Vienna)

The existing read-only CLI preflight succeeded over the operator-selected TP service with python-oracledb 26.0.1 and Oracle Autonomous server **23.26.4.1.0**. Both synchronous and asynchronous native Thin connections used the supplied encrypted PEM wallet over TCPS with certificate identity verification enabled. No application tables were created or changed. Wallet contents, credentials and customer-specific connection identifiers remain outside the repository and PR.

A separate metadata probe ran in a read-only transaction:

| Consumer group | Configured concurrency limit | Parallel degree |
|---|---:|---:|
| HIGH | 3 | 2 |
| MEDIUM | 2 | 2 |
| LOW | 30 | 1 |
| TP | 30 | 1 |
| TPURGENT | 30 | Database default |

These are the actual target's `CS_RESOURCE_MANAGER.LIST_CURRENT_RULES()` results, not a universal Always Free service table or a throughput measurement. Service concurrency and the 30-total-session connection budget are separate constraints.

The session inherited **+02:00** while `DBTIMEZONE` was **+00:00**. UTC initialization for both future Oracle pools is therefore an explicit remaining task, including naive timestamp defaults and comparisons. The aware timestamp variants already have separate non-UTC-session tests, which do not establish UTC behavior for every naive/default path.

Catalog queries found a valid `SYS.DBMS_LOCK` package, visible REQUEST/RELEASE subprograms and a direct EXECUTE privilege with grant option for the supplied administrator. No REQUEST/RELEASE call or grant was executed; the future app user's privileges and mutex behavior on OCI still need verification. The metadata probe found no current application tables in the tested schema; no writable integration suite was run.

## Remaining production blockers

The full Oracle port is incomplete: no Alembic-owned Oracle installation baseline or interrupted-DDL recovery exists yet. Live OCI TLS/wallet connectivity is verified for the supplied administrator; runtime and privilege checks under the eventual app user remain outstanding. The inventory still reports 199 unbounded strings, seven filtered-index definitions and 363 VARCHAR/Text empty-value review entries (569 total). A real Oracle bind/read regression confirms that an empty Python string becomes NULL in a nullable CLOB and fails in a NOT NULL CLOB. These are review items rather than independent task estimates. Additional upserts, bridge/ring ownership, identity/rate-limit locking, reservations/accounting, schema discovery and reports remain to be ported. Bounded query cancellation and connection reclamation are an additional measured blocker: the canceled row-lock test exceeds five seconds on both the frozen SQLAlchemy 2.0.52 / oracledb 26.0.1 stack and an isolated SQLAlchemy 2.0.55 check. Documented native cancel, call-timeout and out-of-band settings, and an isolated oracledb 3.4.2 check did not establish bounded cancellation; no workaround or dependency change was adopted. The strict expected-failure marker accepts only this dedicated deadline exception; unrelated assertion or fixture cleanup failures still fail the test.

Application startup and schema mutation therefore remain explicitly disabled for every Oracle URL. Do not remove that guard on the strength of connection or prepared-coordination tests. The change must remain active until the full task list and single-/two-instance product checks pass.

## Verification and remaining effort

The preparation delta covers 11 requirements and 23 scenarios. The completed tasks cover connection tooling, schema groundwork, the migration mutex, ownership/leader coordination, shared cache invalidation and startup key agreement; full installation/runtime tasks remain incomplete. Independent review found and corrected the CLOB inventory omission and identified the native cancellation blocker. The change is intentionally not archived or marked as an Oracle deployment release.

This is a backend port rather than a driver configuration change: the audit found runtime conflict/upsert constructs across 18 modules, alongside Oracle-specific installation and schema semantics. A planning estimate is roughly **5–10 focused developer days** for a verified fresh installation and two-instance support: about 1–3 for storage/baseline/recovery, 2–4 for remaining query/coordination/accounting paths and 1–3 for OCI setup plus product/failover checks. These ranges overlap and are indicative, not a commitment. The native cancellation limitation may require upstream work and can extend the schedule. Existing-data import is excluded from this estimate; the initial implementation assumes a fresh schema unless the operator asks otherwise.
