# Oracle implementation context

## Current milestone

The operator requested actual single-instance operation on the supplied Autonomous TP database, then explicitly authorized every schema/data test because that database was created solely for this work. HA is deferred. The original two-hour preparation spike and read-only wallet check established the starting point; this milestone adds installation and application runtime.

The live target is Autonomous 23.26.4.1.0, tested with python-oracledb 26.0.1 and frozen SQLAlchemy 2.0.52. Tests use separate application, migration and primitive schemas. Credentials, wallet material and customer-specific connection identifiers remain outside the repository. The runtime uses an application user rather than ADMIN.

## Implemented behavior

- Native Thin request/background pools, each defaulting to four connections and zero overflow, share the existing configurable pool controls. Both physical pools and synchronous migration connections initialize UTC before use.
- A dedicated immutable Oracle Alembic baseline installs 68 tables, 89 indexes, ten sequences and 12 idempotent seeds. Interrupted DDL resumes only after existing-object verification; drift includes defaults, keys, function indexes and sequence properties. Manual stamping and historical SQLite/PostgreSQL replay are rejected.
- Oracle-only string storage preserves empty/NULL/sentinel round trips. Previously unbounded identifiers are limited to 1024 UTF-8 storage bytes, without truncation. Existing bounded Unicode fields retain their supported widths, long URLs/text remain CLOB, CLOB equality checks full values, and conditional uniqueness uses function indexes.
- Existing repository interfaces support Oracle settings/model registry, account identity/token CAS, API-key reservations/settlement, OAuth, sticky/file ownership, scheduler/refresh claims, cache/fingerprint state, auth rate limits, quota decisions, reports/usage folds, bridge continuity and membership.
- Oracle Boolean IS predicates now compile to valid numeric predicates with correct nullable IS/IS NOT behavior. Reporting uses portable CASE sums and Oracle epoch arithmetic.
- Startup, settings updates, account import, API-key creation, proxy streaming with a simulated upstream and real token settlement/request logging, dashboard queries, restart and shutdown have passed through the real application lifecycle on OCI. Network-facing schedulers/upstream responses are stubbed in that smoke; database-only maintenance, leader/ring/cache lifecycle and migrations remain real.

## Connection and cancellation findings

The target's resource-manager rules reported active-statement concurrency HIGH=3, MEDIUM=2, LOW=30, TP=30 and TPURGENT=30. These are instance-specific active-statement limits, distinct from the total session budget and not a throughput benchmark. The operator selected TP. The live session originally inherited +02:00 while DBTIMEZONE was +00:00, motivating per-physical-connection UTC initialization.

Native cancellation-first recovery can wait indefinitely for RESET under a row lock. Shielding/owning native I/O until native timeout recovery completes resolves the strict expected failure without sharing an in-flight session or replaying commits. A row-lock cancellation test obtains a usable connection while the competing lock remains held. A local silent-TCP relay additionally proves single-slot recovery under traffic loss. OCI TCPS skips that local TCP relay only.

A five-second native call limit was too short for initial Autonomous Free LOB writes: both the settings seed and account token writes exceeded it. Runtime round trips now allow 15 seconds, with recovery potentially adding another 15 seconds; synchronous migration calls allow 60 seconds. Connections use a ten-second connect timeout. The bounded read-only preflight retains its independent hard subprocess deadline.

## Validation evidence

- OCI installation: seven fresh/repeat/interrupted-DDL, drift, CLOB/empty/sentinel and invitation-uniqueness tests passed.
- OCI repositories: four native tests passed across account/token updates, OAuth/sticky/planner operations, concurrent settings upserts, reservation settlement/rate limiting, trends/facets, bridge CLOB aliases/retry CAS and ring heartbeat.
- OCI real application subprocess: fresh installation, core API persistence, API-key usage accounting, restart and shutdown passed. A separate repeat against the persistent application schema passed without bypassing the runtime guard.
- OCI historical folds: dashboard bucket reads before/after lifetime, hourly, conversation and report folding passed.
- Oracle unit/migration/configuration selection: 159 passed. SQLite lifecycle/rollup/report/reset-credit regression selections passed (15 and 77 tests); overlapping agent selections are not added to these counts.
- `make lint` passed all architecture, cancellation, timing, settings-tier and migration-topology checks plus Ruff/format. Full `ty check` passed. Strict OpenSpec change and Oracle capability validation passed.
- Final complete OCI Oracle integration suite: **53 passed, one skipped** in 259.42 seconds. The only skip is the local plain-TCP silent-relay injection; the native local suite covered that fault separately. This combined run includes baseline installation/recovery, wallet/UTC, primitives, real application startup/accounting/restart and historical folds. Earlier selections overlap and are not summed.
- Five additional existing SQLite product-path smoke tests passed: settings updates, account import, API-key CRUD, key usage/request-log linkage and streaming proxy persistence.
- `codex-lb-db check` on the persistent OCI application schema reports `migration_policy=ok` and `schema_drift=none`. All 68 main specifications passed strict validation.
- Follow-up Oracle Free CI reproduction found ORA-02014 in startup bridge retention (`FETCH FIRST ... FOR UPDATE`), although Autonomous accepted the query. Candidate IDs now carry the batch limit in an independent subquery before the eligible operation/session join is locked. Cost backfill uses the same approach. The local Oracle Free full application start/persistence/restart/shutdown regression passed after the fix; 20 existing SQLite retention/ownership regressions and three existing SQLite cost-backfill product-path tests passed. Repository fixture installation now uses the production synchronous migration connection and its 60-second DDL timeout; application operations retain the 15-second runtime bound.
- Final follow-up: the complete local `make test-oracle` run passed **57 tests** in 191.94 seconds, including the real application subprocess. The three new OCI batch/ownership/backfill cases passed in 244.17 seconds after the fixture correction. Full type checking and targeted Ruff/format checks passed; the full lint gate and all 68 strict main specifications also passed. These follow-up selections overlap earlier coverage and are not summed.

## Remaining scope

The current milestone is one application instance and fresh Oracle installation. Two-instance host-loss/failover, lease takeover across full application instances, duplicate-refresh prevention during host failure and measured peak connection budgets are deferred. Existing SQLite/PostgreSQL data migration to Oracle is not automatic. Broader long-history/report/retention parity and workload capacity testing remain useful follow-up coverage.

The active change remains unarchived because its original HA checklist is incomplete. Stable operation guidance lives in [the capability context](../../specs/oracle-database/context.md) and [the rendered database guide](../../../docs/database.md).
