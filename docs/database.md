# Database

SQLite is the default database backend and needs no configuration. PostgreSQL is optional via `CODEX_LB_DATABASE_URL` (for example `postgresql+asyncpg://codex_lb:codex_lb@127.0.0.1:5432/codex_lb`).

## Oracle Autonomous Database preparation

Oracle application startup and schema migrations are not supported yet. Experimental preparation tools can check a future Oracle connection and inventory the remaining schema work. They do not enable an Oracle deployment.

Install the optional driver with `uv sync --frozen --extra oracle`. After supplying an `oracle+oracledb://` URL through a protected `CODEX_LB_DATABASE_URL` environment variable, check both Thin connection modes with:

```sh
uv run --extra oracle codex-lb-db oracle-check \
  --pool-size 4 --max-overflow 0 --replicas 2 --extra-replicas 1
```

The check is read-only. Add `--budget-only` to skip connecting: the example budgets 16 application sessions normally and 24 while an extra replica overlaps an update, leaving six under Always Free's 30-session limit. The calculation does not measure throughput or establish HA readiness. Pool arguments affect this check only.

`uv run codex-lb-db oracle-schema --json` produces a complete offline inventory of unresolved schema representations and exits unsuccessfully while blockers remain; it needs neither the Oracle driver nor a database connection.

For TLS/wallet setup, the planned two-instance topology, recovery limits and current support boundaries, see the owning [Oracle preparation capability](https://github.com/maisi/codex-lb/tree/main/openspec/specs/oracle-database).

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
