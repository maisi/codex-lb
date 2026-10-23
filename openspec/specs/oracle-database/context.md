# Oracle database preparation

## Scope

Oracle Autonomous Transaction Processing Always Free is the intended target: one application instance initially, then two sharing the database. The current draft provides connection validation, an offline schema inventory, Oracle timestamp/hash/sequence representations, a migration mutex, file ownership and scheduler leader coordination. Application startup and schema mutation remain disabled for Oracle until installation, runtime queries and accounting have been ported and verified. The supported production backends remain SQLite and PostgreSQL.

The preparation requirements are defined in [the specification](spec.md). The full-port work remains tracked in [the active change](../../changes/add-oracle-autonomous-backend/tasks.md). A successful connection check is not evidence that codex-lb can run on Oracle.

## Preparation commands

Install the optional Thin driver with `uv sync --frozen --extra oracle`. It does not require Oracle Instant Client. Supply `CODEX_LB_DATABASE_URL` through a protected environment/secret source; do not put real passwords or wallet passwords in shell history, logs or a PR. The native URL form is `oracle+oracledb://user:password@host:1522/?service_name=service&protocol=tcps`.

Inspect connection budgets without opening a connection:

```sh
uv run --extra oracle codex-lb-db oracle-check --budget-only \
  --pool-size 4 --max-overflow 0 --replicas 2 --extra-replicas 1
```

This reports 16 steady-state application sessions, 24 during one extra replica's update overlap, and six remaining under the default limit of 30. It counts both independent application pools. The reserve must cover migration/administration connections and temporary disconnected sessions; it is not a measured throughput guarantee. `--pool-size` and `--max-overflow` affect the preparation calculation only. The future deployment must use matching existing `CODEX_LB_DATABASE_POOL_SIZE` and `CODEX_LB_DATABASE_MAX_OVERFLOW` settings on every instance.

Remove `--budget-only` to check both synchronous and asynchronous native Thin connections sequentially. The command performs `SELECT 1 FROM DUAL`, applies an overall worker deadline (`--timeout-seconds`, default 10, maximum 300), and reports sanitized driver error codes. It releases owned connections and does not create or stamp application tables.

Inspect the unresolved schema decisions without a driver, database URL or network:

```sh
uv run codex-lb-db oracle-schema
uv run codex-lb-db oracle-schema --json
```

The inventory exits unsuccessfully while blockers remain. It reports unbounded strings, filtered-index semantics and empty-VARCHAR semantics. The entries are review items, not independent engineering tasks; several entries can be resolved by one explicit storage design.

## Connection and wallet configuration

One-way TLS can connect without a wallet when enabled on the Autonomous instance and the client is allowed by its network access rules. For mutual TLS, mount the downloaded Thin wallet material (`tnsnames.ora`, `ewallet.pem`) at a protected path and provide `config_dir`, `wallet_location` and `wallet_password` URL options as required. Certificate identity verification stays enabled. The preflight accepts the native driver URL with either a host/service name or a TNS alias; it rejects unknown/repeated options and privileged/password-change options.

See the official [python-oracledb connection guide](https://python-oracledb.readthedocs.io/en/stable/user_guide/connection_handling.html) for the current OCI TLS and mTLS prerequisites. Local Oracle Free tests exercise SQL/driver behavior and do not replace OCI certificate, wallet or network validation.

## Storage and migration decisions

Generic Oracle DATE loses fractional seconds. Oracle-specific timestamp representations therefore preserve microseconds, normalize aware instants to UTC and cover SELECT as well as DML RETURNING under non-UTC sessions. Fixed invitation hashes use RAW(32), and generated integer IDs have named Oracle sequences. SQLite/PostgreSQL schema output remains unchanged.

An Oracle Alembic baseline must explicitly create those sequences and preserve historical migration governance. Creating current ORM metadata and stamping it as head is not a supported installation strategy. Bounded string storage, empty strings versus NULL, partial uniqueness, retry behavior after implicit DDL commits, and model/schema drift remain installation blockers.

The prepared migration mutex uses a dedicated Oracle session and `SYS.DBMS_LOCK`; it must survive commits on other connections. The database user needs EXECUTE on that package. No unlocked fallback is allowed. Local test permissions do not establish that an OCI tenant grants the same package access; verify this on the target database before installation is enabled.

## Two-instance topology and failure modes

After the Oracle runtime port is verified, the intended topology is a health-aware load balancer, two independently addressable application instances and one shared database. Both instances share encryption-key material, use unique bridge instance IDs and directly reachable peer URLs, and keep leader election enabled. Each instance runs one application worker. See the current [replica topology contract](../replica-operations/spec.md), which presently requires PostgreSQL.

This topology can tolerate an application-host failure. Active HTTP/WebSocket streams on the failed host may terminate, and failover still observes ownership leases. The common database remains a dependency for both hosts. Always Free does not provide Autonomous Data Guard or restore to a selected historical backup/timestamp; plan external exports and recovery separately. Its 20 GB storage budget also makes log/usage retention relevant; retention is disabled by default in the current application.

Official limits: [Oracle Always Free Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-always-free.html).

## Developer verification

`make test-oracle` requires `CODEX_LB_TEST_ORACLE_URL` pointing to an owned, disposable Oracle test schema. The test suite creates and removes its own probe objects and requires no pre-existing `file_account_pins` or `scheduler_leader` table. Do not supply production credentials. Migration-lock tests additionally require EXECUTE on SYS.DBMS_LOCK. The pinned Oracle Free CI container receives that permission only for its disposable test user.

Until the full runtime and installation checklist passes against Oracle, the active change remains unarchived and the PR remains draft.
