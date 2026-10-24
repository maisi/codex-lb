## Why

An existing SQLite installation cannot move its complete state to the supported Oracle backend: schema upgrades and account import do not transfer API keys, settings, history, or coordination records. Operators need an explicitly invoked, verified offline transfer that preserves encrypted data and leaves the original installation available for recovery.

## What Changes

- Add `codex-lb-db migrate-to-oracle` to transfer every application table from a stopped SQLite installation into a fresh, dedicated Oracle schema.
- Snapshot and upgrade the source privately, validate source integrity and encryption material, and reject incompatible values before transferring data.
- Copy and verify all rows in one Oracle data transaction; retain the separate Oracle migration lineage and refuse used destinations.
- Provide a read-only dry run, bounded batches, safe progress/error output, and a recovery/cutover runbook that preserves the existing encryption key and filesystem archives.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `oracle-database`: Define complete, explicitly invoked SQLite-to-Oracle state transfer, validation, transaction, and cutover contracts.

## Impact

- Database CLI, SQLite lifecycle/migration locking, Oracle baseline inspection, metadata-based row transfer, generated identifier sequences, and Oracle codecs.
- Regression coverage at the CLI/transfer boundary and optional real-Oracle integration coverage.
- Oracle capability requirements/context and the existing database documentation; no new setting, runtime behavior, or dependency beyond the existing Oracle extra.
