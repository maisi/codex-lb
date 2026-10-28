# Oracle operation

## Scope and evidence

codex-lb can use Oracle Autonomous Transaction Processing with the optional native Thin driver. The single-instance milestone was exercised against the operator's OCI Always Free database over the selected **TP** service, using an encrypted PEM wallet, TCPS and certificate identity verification. Application startup, dashboard settings, account import, API-key creation, a simulated upstream response with real reservation/settlement and request logging, restart and shutdown use the real application lifecycle. The [two-instance process-failover context](../replica-operations/oracle-ha.md) extends that acceptance boundary; real upstream credentials and physical-host/network-partition failures remain separate work.

Requirements live in [spec.md](spec.md). The original [Oracle backend change](../../changes/add-oracle-autonomous-backend/tasks.md) tracks the broader backend work. No customer-specific connection identifiers, wallet contents or credentials belong in the repository.

## Installation and connection configuration

Install the optional driver with `uv sync --frozen --extra oracle`. Oracle Instant Client is unnecessary. Use an isolated application user with CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, an appropriate tablespace quota, and EXECUTE on SYS.DBMS_LOCK. The application user owns its own tables; the runtime does not need the administrator account. Grant these privileges through the database's administrative tooling.

Supply `CODEX_LB_DATABASE_URL` through a protected secret/environment file. Passwords and wallet passwords must be URL encoded; SQLAlchemy's `URL.create(...).render_as_string(hide_password=False)` can construct the value without writing it to shell history or logs. The canonical URL uses `oracle+oracledb://` and either a host/service name or a TNS alias.

For mutual TLS, mount `tnsnames.ora` and the encrypted `ewallet.pem` at a protected path, and supply the `config_dir`, `wallet_location` and `wallet_password` URL options. One-way TLS can operate without a wallet when enabled on the database and permitted by its network rules. Unknown/repeated URL options and privileged/password-change options are rejected. Certificate identity verification remains enabled.

After configuring the protected environment, run:

```sh
uv run --extra oracle codex-lb-db oracle-check
uv run --extra oracle codex-lb-db upgrade head
uv run --extra oracle codex-lb-db check
uv run --extra oracle codex-lb --host 127.0.0.1 --port 2455
```

Startup also applies migrations when the existing `database_migrate_on_startup` setting is enabled. The separate Oracle Alembic lineage installs an immutable snapshot: 68 tables, 89 indexes, ten sequences and idempotent preset/settings/watermark seeds. Each existing object is verified before interrupted DDL is resumed. Oracle DDL commits implicitly, so installation never substitutes live ORM `create_all` plus a manual stamp for a versioned migration. Manual Oracle stamping and replaying the SQLite/PostgreSQL Alembic history are rejected. Downgrading the initial Oracle baseline is unsupported.

The migration mutex holds a dedicated DBMS_LOCK session across DDL commits and releases it on failure or process loss. Missing package permissions fail explicitly. Keep the encryption key/data directory stable across restarts: the first stored fingerprint detects a different key before encrypted account data is used. Backing up that directory preserves the encryption key and archives; Oracle data itself needs a database export/recovery procedure.

## Pool budgets, UTC and bounded cleanup

Oracle defaults to **four connections and zero overflow in each of two independent pools**, for eight application sessions per instance. Existing explicit pool settings remain authoritative, and a budget consuming all 30 Always Free sessions is rejected before connecting. Other backends retain their existing defaults. Reserve additional connections for the two-connection migration peak and administration.

`oracle-check --budget-only` opens no database connection. For example:

```sh
uv run --extra oracle codex-lb-db oracle-check --budget-only \
  --pool-size 4 --max-overflow 0 --replicas 2 --extra-replicas 1
```

The two-instance pilot budgets 16 normal sessions and 24 during update overlap, leaving six. This command is a capacity calculation, not a throughput measurement or availability guarantee; real-process acceptance separately exercises all application pool slots. Pool arguments affect the check only.

Every physical request/background and migration connection initializes UTC before application statements. This matters because the target inherited SESSIONTIMEZONE +02:00 while DBTIMEZONE was +00:00. Timestamp variants retain microseconds and normalize aware instants, including SELECT and RETURNING.

Native async I/O stays owned and shielded until completion or native timeout recovery, before caller cancellation propagates. This avoids the driver's cancellation-first RESET hang, while preventing simultaneous use of an in-flight session. Runtime calls allow 15 seconds per native round trip; recovery can add another 15 seconds. Initial Autonomous Free LOB writes exceeded a five-second limit, so synchronous migration calls have a separate 60-second bound. Native connect timeout is ten seconds. Interrupted commits are never automatically replayed.

The read-only `oracle-check` performs synchronous and asynchronous `SELECT 1 FROM DUAL` checks in a subprocess with an overall deadline (default ten, maximum 300 seconds). It reports safe diagnostics and closes owned resources. A successful check establishes connectivity only.

## Storage contracts and limits

Oracle-specific variants preserve SQLite/PostgreSQL DDL. Oracle stores previously unbounded identifier/dimension strings in **1024 UTF-8 bytes**; oversized values fail explicitly and are never truncated. Existing bounded character fields reserve their Unicode width, and free-form text/long URLs remain CLOBs. This Oracle-specific identifier limit should be checked when importing unusually long external IDs.

Empty string and NULL remain distinct through a reversible Oracle-only codec: empty stores U+0001, and values beginning with U+0001 escape that prefix. Both VARCHAR and CLOB values use the codec. Conditional indexes use CASE expressions to preserve filtered uniqueness. CLOB equality uses an indexed 512-character prefix as a candidate filter and authoritative DBMS_LOB.COMPARE for the complete value; prefix collisions cannot establish equality. Invitation hashes use RAW(32); numeric generated IDs use named sequences.

`codex-lb-db oracle-schema [--json]` reports the offline model inventory without loading the driver or opening a connection. Unresolved custom representations cause an unsuccessful exit; a zero-blocker inventory does not verify a running deployment. `codex-lb-db check` additionally compares the installed tables, defaults, constraints, function indexes and sequences against expected storage.

## TP, Free limits and process failover

The tested target ran Autonomous **23.26.4.1.0** with python-oracledb 26.0.1. Its actual resource-manager rules reported TP active-statement concurrency 30 and HIGH concurrency three. Active-statement concurrency differs from the 30-total-session connection budget. Oracle recommends TP or LOW for short OLTP work; see [service names](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/predefined-database-services-names.html).

The pilot topology is a health-aware load balancer, two separately addressable single-worker instances and a shared database. Shared encryption material, distinct bridge IDs/peer addresses and leader election remain necessary. The [operator guide](../../../docs/deployment/oracle-ha.md) covers rollout, bounded drain, client retry and the application connection budget. The [replica topology contract](../replica-operations/spec.md) and [pilot context](../replica-operations/oracle-ha.md) define its limits: an active stream can break, uncertain requests are not automatically replayed, and expired reservations follow the existing conservative cleanup policy. Database and gateway failover remain external infrastructure concerns.

The shared database is a dependency for both application hosts. Always Free's documented storage budget is 20 GB, so log/usage retention matters. Autonomous Data Guard and point-in-time restore to a selected historical backup/timestamp are unavailable on Always Free; plan external exports and recovery. See [official Free limits](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-always-free.html).

## Complete offline SQLite transfer

For copy-and-run Docker commands, use the [compact migration runbook](docker-migration-runbook.md).

The host-side `scripts/migrate-sqlite-to-oracle-docker.sh` orchestrates those commands. Default/explicit dry run requires a stopped source and changes no Oracle data; `--apply` checks image/connectivity, reserves a private backup, stops and copies the source directory, then invokes the existing dry run, transfer and schema check. `--build` is opt-in. All helpers share environment/network/mount arguments and bypass image startup. The script rejects missing source data mounts, inherited application-code mounts and existing backup targets. It retains partial backups on failure, never restarts an installation or retries transfer, and prints a quoted cutover example. External key/wallet backups and stopping other workers/orchestrators remain operator responsibilities.

`codex-lb-db migrate-to-oracle` moves all current application tables from a stopped SQLite installation into a fresh dedicated Oracle schema. It includes accounts, API keys, dashboard users/settings, history, conversations and coordination records. SQLite migration ledgers and deliberately retired physical fields are not part of the Oracle application schema. The [requirements](spec.md) govern completeness, source preservation, pristine-target checks and verification.

Stop all source and target processes, back up the complete source data directory, install the Oracle extra and configure a protected Oracle URL/wallet. Then, with the existing data directory accessible:

```sh
uv run --extra oracle codex-lb-db migrate-to-oracle \
  --source-sqlite /var/lib/codex-lb/store.db --dry-run
uv run --extra oracle codex-lb-db migrate-to-oracle \
  --source-sqlite /var/lib/codex-lb/store.db
uv run --extra oracle codex-lb-db check
```

The target comes from `CODEX_LB_DATABASE_URL` or the existing global `--db-url` option. The key defaults to the source database's sibling `encryption.key`; a separately configured key uses `--source-key-file`. The tool never generates a replacement key or edits runtime configuration. Reuse the same data directory/key/archive volume when starting Oracle, or separately copy that complete directory when relocating hosts. Filesystem archives are not stored in Oracle.

The source stays fenced against application startup, schema migrations and independent writers. A private SQLite backup is upgraded through its own migration history before validation and transfer; the original remains unchanged. Preflight checks integrity, foreign keys, schema compatibility, every encrypted field and Oracle value limits. Dry run performs source preflight and read-only target inspection without installing schema or advancing sequences.

The target must be empty or contain only exact baseline seed values, apart from generated seed timestamps. Schema installation uses the existing Oracle lineage. Sequence advancement happens before copying because Oracle DDL commits implicitly. Exclusive table locks then guard the transaction that verifies the pristine baseline and commits the `oracle_transfer_incomplete` startup fence. Seed removal, bounded typed inserts and self-reference restoration then commit batch by batch, each table is verified by row count and digest, and a final transaction removes the fence. A single transaction exhausted Always Free's fixed ~2.3 GB undo (`ORA-30036`) on a 4.3-million-row installation. The existing migration-lock timeout governs target mutex waits; `--batch-size` bounds rows per batch (default 500, maximum 10000).

Copy or verification failure leaves committed batches behind the fence; startup refuses the target and a repeated transfer clears and recopies it (no resume or upsert). Installed schema and harmless sequence gaps can remain. Failures are never automatically replayed. Returning to the unchanged SQLite source after Oracle accepts new writes would discard those new writes, so retain the backup until application acceptance completes.

Regression coverage populates all 68 application tables and exercises source immutability, old-schema snapshot upgrades, cycles, ciphertext/empty/NULL/CLOB/timestamp fidelity, wrong keys, oversized values, used-target rejection, rollback/retry and order-independent checksums. The optional destructive `test_oracle_transfer.py` runs through the existing Oracle CI glob against `CODEX_LB_TEST_ORACLE_BASELINE_URL`, including generated IDs after import. Local implementation verification did not have that disposable Oracle URL and therefore does not establish a live migration acceptance result.

## Developer verification

### Docker transfer packaging

Both Docker dependency stages install the locked `oracle` extra, including native Thin driver wheels for the images' Python 3.14. Runtime images remain installer-free. Build a new image from the updated checkout until a containing release is published; an older `latest` cannot supply this new CLI.

For a stopped container named `codex-lb`, preserve its mounts with `--volumes-from codex-lb` and run `--entrypoint python codex-lb:oracle -m app.db.migrate migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db --dry-run`, then repeat without `--dry-run`. This bypasses startup migrations. Supply the Oracle URL and preserved runtime configuration through a protected environment file; volume inheritance does not inherit networks or environment. Add the required container network and read-only wallet mount for every migration/check/application command. Keep the old container and complete data backup through acceptance. The detailed backup and startup commands are rendered in the database guide.

Packaging verification inspected both frozen dependency commands, the locked driver's Python 3.14 wheel availability and direct CLI help. Docker daemon access was unavailable locally; these changes do not claim a locally built/tested image.

### Test schema isolation

`make test-oracle` uses disposable test schemas. `CODEX_LB_TEST_ORACLE_URL` covers primitives and repository paths; `CODEX_LB_TEST_ORACLE_BASELINE_URL` isolates destructive fresh/interrupted/drift tests; `CODEX_LB_TEST_ORACLE_RUNTIME_URL` isolates the real application subprocess; `CODEX_LB_TEST_ORACLE_HA_URL` isolates real-process failover with native HAProxy. Each user requires the installation permissions above. Runtime/repository probes refuse pre-existing tables and remove only their owned application objects; the HA harness also refuses pre-existing views and sequences. Baseline tests explicitly reset their dedicated schema.

The Oracle CI workflow creates separate users for installation and application smoke tests. It verifies a canceled row-lock wait and recovery of the same single-slot pool while the blocker remains held; a local TCP relay also verifies cancellation with silent traffic. TLS targets skip that local TCP fault injection, while wallet/UTC, row-lock cancellation and actual OCI writes are tested separately. The former strict cancellation expected failure has been removed after native-timeout-first ownership passed.

Oracle Free rejects a top-level `FETCH FIRST ... FOR UPDATE` in bridge retention and abandonment scans with ORA-02014. These paths bound candidate operation IDs in an independent subquery, then lock the eligible operation/session join without an outer row limit. Original eligibility filters and the deletion-time recheck preserve the live owner's duplicate-suppression ledger. Cost-backfill batches use the same selection pattern, preserving log eligibility, ID ordering and resume cursors.

Related upstream context: [python-oracledb cancellation recovery](https://github.com/oracle/python-oracledb/issues/623), [SQLAlchemy Oracle termination](https://github.com/sqlalchemy/sqlalchemy/issues/13578), and the [driver connection guide](https://python-oracledb.readthedocs.io/en/stable/user_guide/connection_handling.html).
