# Complete SQLite to Oracle transfer

## Purpose and scope

Move an existing stopped installation, including API keys, settings, history, and internal application state, into the dedicated Oracle backend. The [delta requirements](specs/oracle-database/spec.md) define the contract. Account export/import is insufficient because it leaves most application tables behind.

## Operational example

With every SQLite process stopped, a protected Oracle URL in the environment, and the existing data directory mounted at `/var/lib/codex-lb`:

```sh
uv run --extra oracle codex-lb-db migrate-to-oracle \
  --source-sqlite /var/lib/codex-lb/store.db --dry-run
uv run --extra oracle codex-lb-db migrate-to-oracle \
  --source-sqlite /var/lib/codex-lb/store.db
uv run --extra oracle codex-lb-db check
```

The sibling `encryption.key` is reused. An installation with a separately configured key supplies `--source-key-file /protected/path/encryption.key` and retains that same key configuration after cutover. The transfer never creates a replacement key or edits the runtime environment.

## Boundaries and decisions

The command moves database rows; encryption material and request/conversation archives remain in the existing data directory/volume. Reusing that volume is the normal path. Relocation uses an ordinary complete data-directory backup/restore in addition to database transfer.

The source is privately snapshotted and upgraded, so the stopped original stays available for recovery. Oracle receives its own baseline and Alembic version; SQLite's ledger is not portable. Fresh-only target acceptance avoids ambiguous merge semantics and accidentally replacing a live installation.

## Failure modes and recovery

Preflight rejects source corruption, broken references, unknown schema, wrong keys, and values Oracle cannot represent. The target data copy rolls back on failure before commit. Oracle schema/sequence preparation can remain because Oracle DDL commits independently; gaps do not affect imported identity preservation. An uncertain commit is never automatically replayed; inspect the target before retrying.

Retain the complete backup and source directory until the Oracle installation passes acceptance. The unchanged SQLite source is a rollback point only for data written before cutover. Once Oracle handles new writes, starting SQLite again would omit those writes.

## Validation evidence

Implementation and validation results are recorded in [tasks.md](tasks.md). This change does not broaden the Oracle single-instance milestone to HA.
