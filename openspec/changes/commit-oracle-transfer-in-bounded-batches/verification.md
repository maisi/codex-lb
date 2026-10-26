## Verification (2026-10-26)

### Failure that motivated the change

Production cutover with the previous single-transaction transfer (image `sha256:e85a388f…`, Always Free ADB 23.26, `ocidb1_tp`): 68 tables / 4,346,708 rows, dry run passed, the transfer rolled back after 49 verified tables. Reproduced against the backup copy with the driver error exposed: `ORA-30036: unable to extend segment by 8 in undo tablespace 'UNDOTBS1'` (2.28 GB). The source was restarted unchanged on SQLite.

### Local checks on this branch

- `pytest tests/unit/test_oracle_transfer.py`: 27 passed (new: fenced interrupted transfer + restart to an exact copy for insert and verification failures, at most one DML batch per committed transaction, startup fence only on Oracle).
- `pytest -m integration tests/integration/test_oracle_transfer.py` against a disposable Always Free schema (`CODEXLB_IT`, dropped afterwards): 2 passed, including the injected mid-transfer failure → marker present, `verify_no_incomplete_oracle_transfer` refuses, dry run reports `target_incomplete_transfer=true`, rerun completes and removes the marker.
- `make lint`, `ty check`, `openspec validate --specs` (68 passed) and `openspec validate commit-oracle-transfer-in-bounded-batches --strict`: passed.

### Production re-run (2026-10-26, UTC)

Image: the pinned base digest `sha256:e85a388f…` (main `e4f95e09`) with this PR's five Python files overlaid; source container stopped and fully backed up first.

- Dry run 23:06–23:12: 68 tables, 4,348,112 rows, `target_incomplete_transfer=false`.
- Transfer 23:12:45–23:48:44 (~36 min, `--batch-size 500`): `oracle_transfer=complete`, all 68 tables verified (incl. `http_bridge_operation_events` 3.17 M rows); no undo error.
- `db check`: `migration_policy=ok`, `schema_drift=none`; marker absent afterwards.
- Application restarted on Oracle 23:51: `/health/ready` 200, counts match the source (4 accounts, 13 API keys, 210,922 request logs, 721,684 usage rows), retained SQLite file untouched.

A first attempt of this run was killed (exit 137) by an unrelated host Docker daemon upgrade during the dry run; nothing had been written to Oracle, and the run was repeated from the same stopped source and backup.
