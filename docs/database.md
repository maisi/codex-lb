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
