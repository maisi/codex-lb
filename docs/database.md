# Database

SQLite is the default database backend and needs no configuration. PostgreSQL is optional via `CODEX_LB_DATABASE_URL` (for example `postgresql+asyncpg://codex_lb:codex_lb@127.0.0.1:5432/codex_lb`).

## Oracle Autonomous Database

Experimental Oracle operation is available with the optional native Thin driver. Installation, dashboard settings, account import, API keys, proxy accounting/logging and restart have been exercised on OCI over the TP service. The [two-instance failover pilot](deployment/oracle-ha.md) adds a shared-schema topology with process-failure/client-retry acceptance; active streams can still be interrupted.

Install the driver with `uv sync --frozen --extra oracle`, and supply an `oracle+oracledb://` URL and wallet options through a protected `CODEX_LB_DATABASE_URL` secret/environment file. Use a dedicated application schema with CREATE SESSION/TABLE/SEQUENCE, a tablespace quota and EXECUTE on SYS.DBMS_LOCK. Then run:

```sh
uv run --extra oracle codex-lb-db oracle-check
uv run --extra oracle codex-lb-db upgrade head
uv run --extra oracle codex-lb-db check
uv run --extra oracle codex-lb --host 127.0.0.1 --port 2455
```

Oracle defaults to four connections and zero overflow per pool, eight application sessions in total. Explicit existing pool settings override these defaults. Previously unbounded identifier fields have an Oracle-specific limit of 1024 UTF-8 bytes; free-form text remains CLOB. SQLite/PostgreSQL behavior is unchanged.

The read-only connection check and offline `oracle-schema --json` inventory do not establish application or HA readiness. For wallet configuration, migration permissions, storage limits, timeout behavior and acceptance limits, see the owning [Oracle database capability](https://github.com/maisi/codex-lb/tree/main/openspec/specs/oracle-database).

### Move an existing SQLite installation to Oracle

`codex-lb-db migrate-to-oracle` transfers all application database tables, including accounts, API keys, settings, usage, logs, conversations, and internal state. It preserves identifiers and encrypted values and verifies every table before committing. It accepts a fresh dedicated Oracle schema or an unchanged freshly installed Oracle baseline; it refuses a target that already contains application data.

Plan downtime for the complete transfer and acceptance checks. The source database is privately snapshotted and, when needed, upgraded in that temporary copy. The original SQLite database stays unchanged. The transfer does not edit your runtime configuration or move filesystem files: retain the existing encryption key and archives by reusing the same data directory/volume. To move hosts or volumes as well, copy the complete data directory separately using your usual backup/restore procedure.

1. Stop **every** application instance, worker, and maintenance command using the SQLite installation, and keep target application processes stopped as well. Keep them stopped through cutover. Back up the complete data directory, including `store.db`, `encryption.key`, archives, and any SQLite sidecar files.
2. Install the optional Oracle driver and configure the target URL/wallet through a protected environment file as described above. Select a dedicated application schema with enough free space for the source data, indexes, and transfer transaction. Run `uv run --extra oracle codex-lb-db oracle-check`.
3. Run the read-only preflight against your actual source path. This example uses the existing Docker data-directory path; local installations normally use `~/.codex-lb/store.db`:

   ```sh
   uv run --extra oracle codex-lb-db migrate-to-oracle \
     --source-sqlite /var/lib/codex-lb/store.db --dry-run
   ```

   The key defaults to `encryption.key` beside the source database. If you configured another key path, add `--source-key-file /protected/path/encryption.key` to both commands and retain that same runtime key configuration. Dry run checks source integrity, schema, key compatibility, Oracle value limits, and the target without creating Oracle tables or changing rows or sequences. It reports whether target preparation is needed.
4. Run the transfer with the same paths:

   ```sh
   uv run --extra oracle codex-lb-db migrate-to-oracle \
     --source-sqlite /var/lib/codex-lb/store.db
   uv run --extra oracle codex-lb-db check
   ```

   The target defaults to `CODEX_LB_DATABASE_URL`; the existing global `--db-url` option can select a target explicitly. Keep credential-bearing URLs out of shell history. `--batch-size` controls rows per read/write batch and defaults to 500. The command creates the Oracle baseline when needed; a separate `upgrade head` beforehand is optional.
5. After a successful verified transfer, start codex-lb with the Oracle URL and the existing data directory/key/archive volume. Confirm login, accounts, API keys, settings, usage, and logs through the normal application interfaces before reopening traffic. Keep the complete backup until acceptance is finished.

The command never merges into a used target and does not copy SQLite's migration ledger: Oracle keeps its own verified Alembic lineage. A wrong key, broken source relationship, unsupported schema, or value that exceeds Oracle's storage bounds stops preflight without truncating or dropping data.

If copying or verification fails before commit, transferred rows and baseline seed changes roll back together. Oracle schema preparation and sequence advancement can remain because Oracle DDL commits independently; the unchanged pristine target can be retried. If a connection fails during commit, the outcome can be uncertain: inspect the target before retrying instead of clearing it. Diagnostics report status and table counts without printing stored credentials or row contents.

Before Oracle accepts new application writes, recovery can return to the stopped original SQLite installation. After cutover, returning to that SQLite copy would lose subsequent Oracle writes. The complete transfer contract is owned by the [Oracle database specification](https://github.com/maisi/codex-lb/blob/main/openspec/specs/oracle-database/spec.md).

### Run the SQLite transfer from Docker

For the short operational checklist, use the [compact Docker migration runbook](https://github.com/maisi/codex-lb/blob/main/openspec/specs/oracle-database/docker-migration-runbook.md).

To automate that checklist from the updated checkout, create your protected `.env.oracle` and run:

```sh
bash scripts/migrate-sqlite-to-oracle-docker.sh --env-file .env.oracle --build --apply
```

The script checks image/connectivity, stops `codex-lb`, saves a new private data-directory backup, and runs dry-run, transfer and schema check. It prints a separate application start command and never restarts an application on failure. Without `--apply` it only validates and requires a stopped source. Add `--network` and repeatable `--mount` options for the Oracle connection/wallet; `--help` covers custom paths and image/container names. Back up external keys/wallets separately. The following commands remain the manual alternative.

Both Dockerfiles include the Oracle Thin driver. Until a release containing the transfer is published, build the image from the updated checkout; pulling an older `latest` image will not include the command. These examples assume the existing container is named `codex-lb` and uses `/var/lib/codex-lb/store.db`. Substitute your actual container name/path.

```sh
docker build -t codex-lb:oracle .
docker stop codex-lb
docker cp codex-lb:/var/lib/codex-lb ./codex-lb-backup-before-oracle
```

Keep the old container stopped and retain the backup. Create a protected `.env.oracle` file (`chmod 600 .env.oracle`) containing `CODEX_LB_DATABASE_URL` with your Oracle connection URL; preserve any existing data-directory/key configuration. The host in that URL must be reachable from the temporary containers. `localhost` means the temporary container itself.

Run the CLI directly, reusing the old container's mounts:

```sh
docker run --rm --volumes-from codex-lb --env-file .env.oracle \
  --entrypoint python codex-lb:oracle -m app.db.migrate \
  migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db --dry-run

docker run --rm --volumes-from codex-lb --env-file .env.oracle \
  --entrypoint python codex-lb:oracle -m app.db.migrate \
  migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db

docker run --rm --volumes-from codex-lb --env-file .env.oracle \
  --entrypoint python codex-lb:oracle -m app.db.migrate check
```

`--entrypoint python` bypasses normal application startup, including its automatic upgrade, so nothing runs before the requested dry run. `--volumes-from` reuses mounts from a stopped container but does not inherit its environment or network. If Oracle requires a particular Docker network, add `--network YOUR_NETWORK` to every command. If the URL uses a wallet, mount its directory read-only in every temporary container and the new application container, with paths matching the URL options. A custom source key adds `--source-key-file` as above.

After successful transfer/check, start the new application using `codex-lb:oracle`, the same data mounts, the Oracle environment, and your existing ports, network and other runtime settings. For the basic Docker deployment, with all required settings in `.env.oracle`:

```sh
docker run -d --name codex-lb-oracle \
  --volumes-from codex-lb --env-file .env.oracle \
  -p 2455:2455 -p 1455:1455 --restart unless-stopped \
  codex-lb:oracle
```

For Compose, keep the existing volume declaration and use the updated image/build and Oracle environment in the service. One-shot commands use `docker compose run --rm --no-deps --entrypoint python server -m app.db.migrate ...` after `docker compose stop server`; replace `server` and supply your normal `-f` arguments as needed. Do not run `docker compose down -v`, because that deletes the source volume. Keep the old container/volume until application acceptance; start only the Oracle instance after cutover.

## Data paths

| Environment | Path |
|-------------|------|
| Local / uvx | `~/.codex-lb/` |
| Docker | `/var/lib/codex-lb/` |

Backup this directory to preserve your data (database, encryption key, archives).

## PostgreSQL via Docker Compose

The Docker Compose `postgres` profile uses the Postgres 18 image and mounts the named data volume at
`/var/lib/postgresql`, the parent of the image's versioned `PGDATA` directory. The `postgres` and
`postgres-upgrade` profiles live in the root
[`docker-compose.yml`](https://github.com/Soju06/codex-lb/blob/main/docker-compose.yml)
(`docker-compose.prod.yml` only defines the `server` service, for external PostgreSQL).

## Upgrading Postgres 16 → 18

Existing Postgres 16 compose volumes must be upgraded before the Postgres 18 container starts:

```bash
docker compose --profile postgres stop postgres
docker run --rm -v codex-lb-postgres-data:/var/lib/postgresql -v "$PWD:/backup" alpine \
  tar -C /var/lib/postgresql -czf /backup/codex-lb-postgres-data-before-pg18.tgz .
docker compose --profile postgres-upgrade run --rm postgres-upgrade
docker compose --profile postgres up -d postgres
```

The `postgres-upgrade` profile runs `pg_upgrade` in one-shot mode against the same named volume and exits after the
data directory has been upgraded to the Postgres 18 layout. Because that helper mounts and rewrites the operator's
database volume, Compose pins the helper image by digest; refresh and review the digest deliberately when changing the
helper image tag. Keep the backup until the application has started and `codex-lb-db check` succeeds against the
upgraded database.

The normal `postgres` service refuses to start when it detects the old root-level `PG_VERSION` file from a pre-18
Compose volume. If that guard fires, run the `postgres-upgrade` profile above before starting Postgres again.
It also refuses nested `/var/lib/postgresql/data` directories that still report a pre-18 major version, because those
layouts need an explicit pg_upgrade before the Postgres 18 container can safely open them.

---

## Advisory migration measurements

Developers can measure selected Alembic revisions with deterministic synthetic accounts and request logs on an empty, owned PostgreSQL database. The explicitly invoked benchmark produces JSON and Markdown reports; durations do not determine pass or fail. Follow the [benchmark guide](https://github.com/Soju06/codex-lb/blob/main/openspec/specs/migration-benchmark/context.md) for target isolation, fixture parameters and transaction limits.

*Specs: [database-backends](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/database-backends) · [database-migrations](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/database-migrations) · [migration-benchmark](https://github.com/Soju06/codex-lb/tree/main/openspec/specs/migration-benchmark)*
