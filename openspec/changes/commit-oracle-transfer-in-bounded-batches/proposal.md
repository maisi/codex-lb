## Why

A real 6.4 GB SQLite installation (4.3 million rows) could not be transferred to Oracle Autonomous Database Always Free. The transfer wrote every table in one Oracle transaction and failed with `ORA-30036: unable to extend segment ... in undo tablespace 'UNDOTBS1'` after 49 of 68 tables. Always Free undo is fixed (about 2.3 GB) and cannot be enlarged, so production-sized installations cannot migrate at all.

## What Changes

- Commit every bounded transfer batch (seed clearing, row copy, self-reference restoration) in its own Oracle transaction, so undo use is bounded by `--batch-size` instead of the installation size.
- Commit an `oracle_transfer_incomplete` marker in `runtime_sentinels` before the first data batch and remove it only after every table is verified. Application startup refuses an Oracle database that carries the marker.
- A repeated `migrate-to-oracle` against a marked target restarts from a cleared target; it never resumes or upserts. Unmarked used targets are still rejected.
- Dry run reports whether the target holds an incomplete transfer; the failure diagnostic explains the fence and the restart path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `oracle-database`: Replace the single data transaction with bounded committed batches behind a startup fence; define restart of an incomplete transfer and its dry-run/diagnostic reporting.

## Impact

`app/db/oracle_transfer.py`, `app/db/oracle_transfer_target.py`, a startup check in `app/main.py`, CLI output in `app/db/migrate.py`, unit and real-Oracle tests, the Docker runbook and Oracle context. No schema migration, dependency or new setting is added.

Fixes the production cutover blocker observed on 2026-10-26 (no GitHub issue).
