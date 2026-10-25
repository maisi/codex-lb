## 1. Source snapshot and preflight

- [x] 1.1 Add stopped-source lifetime/migration locking and a SQLite write fence; create, upgrade, and clean up a private snapshot without modifying the original.
- [x] 1.2 Validate snapshot integrity, foreign keys, current application-table/column inventory, the existing encryption key/fingerprint, encrypted fields, and Oracle value representability.
- [x] 1.3 Build metadata-driven bounded row iteration, typed order-independent table digests, dependency ordering, and nullable self-reference restoration support.

## 2. Oracle destination and transfer

- [x] 2.1 Inspect and verify fresh/pristine-only Oracle destinations under the existing migration mutex, preserving the separate Oracle lineage and rejecting changed baseline seeds or used targets.
- [x] 2.2 Prepare Oracle baseline and advance generated-identifier sequences before data DML; fence target tables against concurrent writes during transfer.
- [x] 2.3 Copy all application tables, remove baseline seeds, restore references, and verify full row digests/counts within one rollback-safe Oracle data transaction.

## 3. CLI and operator documentation

- [x] 3.1 Expose `migrate-to-oracle` with source/key/batch/dry-run options, existing target selection, sanitized output, and resource cleanup on every exit path.
- [x] 3.2 Document backup, source downtime, Oracle preparation, dry run, transfer, same-key/data-volume cutover, acceptance checks, and rollback limitations in the existing database guide.

## 4. Verification and specification sync

- [x] 4.1 Add regression coverage at the CLI/transfer path for complete data preservation, old-source snapshot upgrades, live-source rejection, incorrect keys/unsupported schema, dry-run immutability, pristine-target rejection, rollback, digest mismatch, and identity/reference preservation.
- [x] 4.2 Run focused tests and lint/type checks, execute isolated real-Oracle transfer coverage when available, and record any unavailable acceptance environment explicitly.
- [x] 4.3 Run strict OpenSpec validation, verify implementation against the artifacts, sync verified requirements/context into the owning main capability, and archive only after verification succeeds.
