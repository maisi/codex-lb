## Context

The Oracle backend has a dedicated immutable Alembic baseline and application-specific codecs for empty strings, fixed hashes, Unicode bounds, timestamps, and generated identifiers. Existing SQLite upgrades preserve one SQLite database, while account import covers only a subset of application state. A complete migration must preserve every metadata-owned application table, encrypted credentials, and filesystem key/archive continuity without replaying SQLite revisions against Oracle.

## Goals / Non-Goals

**Goals:** Transfer the complete state of a stopped supported SQLite installation, prove that the target contains equivalent typed values, preserve the original database for recovery, and document a concrete dry-run/cutover procedure.

**Non-Goals:** Online replication, merge/upsert into a used database, automatic runtime configuration changes, moving filesystem archives, rotating encryption keys, PostgreSQL transfer, and certifying Oracle HA.

## Decisions

1. **Use the database CLI with explicit source and existing target selection.** The command is `codex-lb-db [--db-url TARGET] migrate-to-oracle --source-sqlite PATH [--source-key-file PATH] [--batch-size 500] [--dry-run]`. The target defaults to the existing database URL setting, and the key defaults to the source database's sibling `encryption.key`. This reuses the existing Oracle extra and connection policy instead of introducing configuration. No key creation or configuration mutation occurs.

2. **Keep the original offline and transfer a private upgraded snapshot.** Hold the existing SQLite application-lifetime and migration locks plus a database write fence while making and reading a private SQLite backup. Upgrade that snapshot using the normal SQLite Alembic lineage. This supports older installations while preserving source bytes; reading the live database directly would permit mixed state or mutate the only original during upgrade. Check SQLite integrity, foreign keys, application table/column inventory, encryption key fingerprint, and all encrypted fields before Oracle data mutation.

3. **Discover the complete inventory from application metadata.** Copy every metadata table (currently 68), excluding migration ledgers, with dependency ordering and bounded batches. Validate values using Oracle codecs before mutation. Restore nullable self references in a second pass within the same data transaction. A handwritten table allowlist could silently omit future features; unknown source tables instead fail closed until reviewed.

4. **Require a fresh, dedicated Oracle schema and preserve its lineage.** Inspect the target under the existing DBMS_LOCK migration mutex, let the normal upgrade command prepare the immutable Oracle baseline under that same mutex, then reacquire it and revalidate before transfer. The separate scopes avoid recursive acquisition on different database sessions. A preinstalled schema is accepted only when its objects and seed contents match a pristine baseline, ignoring generated seed timestamps. Exclusive table locks fence the final recheck and data transaction. Never clear arbitrary target data. This is a one-way offline copy, so partial imports and upserts are deliberately unsupported.

5. **Separate committing DDL from atomic data work.** Oracle DDL implicitly commits. Prepare/verify schema and advance numeric identifier sequences beyond source maxima before beginning one data transaction. That transaction removes baseline seeds, inserts all rows, restores self references, and verifies every table. On a copy or verification failure, rollback restores pristine baseline rows; prepared objects and sequence gaps may remain. A retry starts again from a pristine target.

6. **Verify complete typed rows, not only counts.** Canonicalize each field with explicit type/NULL boundaries and compute order-independent complete row digests plus counts for every table before commit. This detects truncation, changed values, type loss, and incomplete self-reference restoration even when row counts match. Oracle-only string escapes are decoded through normal result processing before comparison.

7. **Keep dry run read-only and filesystem continuity explicit.** Dry run performs source preparation/preflight and read-only target inspection without migrations, DML, stamping, or sequence advancement. The command reports inventory/status only and sanitizes database/codec errors. Operators reuse the existing data directory/volume or copy it by ordinary volume backup/restore; the database transfer does not copy keys or archives into Oracle.

## Risks / Trade-offs

- **Long offline window and one large Oracle transaction** → bounded batches cap application memory, but operators must reserve downtime and Oracle undo/storage space for their history volume.
- **Source contains incompatible old/custom schema or oversized Oracle identifiers** → preflight fails before target data mutation; no lossy truncation or table omission is attempted.
- **Wrong encryption key would make migrated credentials unusable** → validate fingerprint and decrypt all supported encrypted fields before transfer; retain the same key during runtime cutover.
- **Oracle commits schema/sequence changes independently** → complete those changes before DML and document that a failed transfer can leave a prepared schema and sequence gaps, but no committed partial application copy.
- **Client loses connection during commit** → never automatically replay an uncertain commit; inspect the destination before retrying, and reject used targets.
- **Only a local SQLite write fence can exclude arbitrary SQLite clients** → keep the fence for the entire source lifetime and require all application/maintenance processes to remain stopped through cutover.

## Migration Plan

1. Stop every source application/worker/maintenance process and back up its complete data directory.
2. Install the Oracle extra, configure a protected target URL/wallet, and check connectivity to a dedicated application schema.
3. Run dry run with the original SQLite database and key accessible in the existing data directory.
4. Run transfer, inspect successful table/row verification, and run the normal target schema check.
5. Start the application with Oracle configured and the same data directory/key/archive volume; check accounts, API keys, settings, usage, and logs.
6. Keep the original source backup until acceptance. Before Oracle accepts new writes, recovery can return to the unchanged SQLite source. After Oracle accepts writes, returning to SQLite would lose those new writes and requires a separate recovery decision.

## Open Questions

None required to begin implementation. Real-Oracle transfer verification will use an isolated disposable schema when available; absence of that environment must be reported as an acceptance limitation.
