## Purpose

Make the SQLite → Oracle transfer fit Always Free's fixed undo tablespace without weakening its no-partial-cutover guarantee.

## Observed failure (2026-10-26)

Source: 6.4 GB SQLite, 68 tables, 4,346,708 rows (`http_bridge_operation_events` 3.17 M, `usage_history` 721 k, `request_logs` 211 k). The single data transaction failed after 49 verified tables with `ORA-30036` in `UNDOTBS1` (2.28 GB). The rollback worked and the source was restarted unchanged on SQLite. Reproductions against the same backup failed earlier (at `request_logs`) because the previous attempts' undo was still retained.

## Decisions

- **Batches commit; atomicity moves to a fence.** Instead of one transaction, a committed `runtime_sentinels` row `oracle_transfer_incomplete` marks the target as unusable. It is written in the same transaction that verified the pristine baseline under the table locks, and deleted in the final transaction after every table digest matched. Startup refuses the database while it exists, so a partial copy can never serve traffic.
- **Restart, not resume.** A rerun against a marked target deletes all application rows (marker excepted) in committed primary-key batches and copies everything again. Resuming would need per-row provenance and is not worth the risk for a one-time offline operation. Only the marker distinguishes "our interrupted transfer" from a used target; unmarked targets with data are still rejected.
- **Bound = `--batch-size`.** No new setting. The default of 500 rows keeps undo per transaction in the low megabytes; the commit count (about 9,000 for the observed installation) costs a few minutes of round trips.
- **Locks.** `LOCK TABLE ... NOWAIT` still proves no writer holds uncommitted target rows before the marker commits. Locks end with that commit; afterwards the marker plus the stopped-source/target-process precondition fence writers.

## Failure modes

- Failure before the marker commits: unchanged behaviour, nothing transferred, target remains pristine.
- Failure after the marker commits: committed batches remain, startup is refused, the diagnostic names the restart path (`migrate-to-oracle` again with the stopped source). The SQLite source stays authoritative.
- Never delete the marker by hand unless the transfer is abandoned and the schema is dropped.

## Example

```text
$ python -m app.db.migrate migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db --dry-run
oracle_transfer=dry_run
target_incomplete_transfer=true      # earlier attempt was interrupted; a transfer restarts from a cleared target
$ python -m app.db.migrate migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db
oracle_transfer=complete
```
