# Docker: SQLite → Oracle

Scope: one stopped installation, all application tables, and a fresh dedicated Oracle schema. Contract: [Oracle specification](spec.md); background: [context](context.md).

Keep the existing data volume and encryption key. These examples assume container `codex-lb` and `/var/lib/codex-lb/store.db`. Keep all source/target application processes stopped during transfer. Add any required Docker network and read-only wallet mount to both `db()` and the application command below; `--volumes-from` inherits mounts only.

## 1. Prepare

From this updated repository checkout, build the image. Create `.env.oracle` with your original runtime settings and the target `CODEX_LB_DATABASE_URL` (native `oracle+oracledb://` URL, encoded credentials, wallet options if needed). The target needs CREATE SESSION/TABLE/SEQUENCE, a tablespace quota and EXECUTE on SYS.DBMS_LOCK. Oracle must be reachable from Docker; `localhost` refers to the container itself.

```bash
SOURCE_CONTAINER=codex-lb
IMAGE=codex-lb:oracle
docker build -t "$IMAGE" .
chmod 600 .env.oracle

db() {
  docker run --rm --volumes-from "$SOURCE_CONTAINER" --env-file .env.oracle \
    --entrypoint python "$IMAGE" -m app.db.migrate "$@"
}
db oracle-check
```

## 2. Stop and back up

Keep the old container and its mounts. Store the complete backup outside the repository:

```bash
umask 077
backup_dir="$HOME/codex-lb-backup-$(date +%Y%m%dT%H%M%S)"
docker stop "$SOURCE_CONTAINER"
docker cp "$SOURCE_CONTAINER":/var/lib/codex-lb "$backup_dir"
```

## 3. Validate, transfer, check

Run each command only after the previous command succeeds. A custom key path adds `--source-key-file /path/encryption.key` to both transfer commands.

```bash
db migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db --dry-run
db migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db
db check
```

Expect `oracle_transfer=dry_run`, then `oracle_transfer=complete`, then `migration_policy=ok` and `schema_drift=none`. Stop on any error. Do not start the application against Oracle before the transfer completes.

## 4. Start and accept

Preserve your original network, environment, ports and other Docker options. For the basic deployment, with those settings in `.env.oracle`:

```bash
docker run -d --name codex-lb-oracle \
  --volumes-from "$SOURCE_CONTAINER" --env-file .env.oracle \
  -p 2455:2455 -p 1455:1455 --restart unless-stopped "$IMAGE"
docker logs --tail 100 codex-lb-oracle
```

Check dashboard login, accounts, existing API keys, settings, usage and request logs before reopening traffic. Retain the old container and backup through acceptance. Never run both installations against the shared volume simultaneously.

## Recovery

A failure before the database commit rolls back copied rows; schema and sequence preparation may remain. Inspect an uncertain commit before retrying; never clear a used target. Before accepting new Oracle application writes, stop the new container and run `docker start "$SOURCE_CONTAINER"` to return to unchanged SQLite. After Oracle accepts writes, that SQLite copy lacks those changes; recovery then requires reconciling/exporting Oracle data. Do not delete the volume or run `docker compose down -v`.

For Compose, preserve the service's volume/configuration and replace the helper's `docker run` with `docker compose run --rm --no-deps --entrypoint python server -m app.db.migrate "$@"`; use your actual service name and `-f` arguments. Stop the old service and back up before transfer; recreate it with the Oracle environment only after the transfer/check succeeds.
