## Verification (2026-10-26)

### Failure that motivated the change

Production cutover with the previous single-transaction transfer (image `sha256:e85a388f…`, Always Free ADB 23.26, `ocidb1_tp`): 68 tables / 4,346,708 rows, dry run passed, the transfer rolled back after 49 verified tables. Reproduced against the backup copy with the driver error exposed: `ORA-30036: unable to extend segment by 8 in undo tablespace 'UNDOTBS1'` (2.28 GB). The source was restarted unchanged on SQLite.

### Local checks on this branch

- `pytest tests/unit/test_oracle_transfer.py`: 27 passed (new: fenced interrupted transfer + restart to an exact copy for insert and verification failures, at most one DML batch per committed transaction, startup fence only on Oracle).
- `pytest -m integration tests/integration/test_oracle_transfer.py` against a disposable Always Free schema (`CODEXLB_IT`, dropped afterwards): 2 passed, including the injected mid-transfer failure → marker present, `verify_no_incomplete_oracle_transfer` refuses, dry run reports `target_incomplete_transfer=true`, rerun completes and removes the marker.
- `make lint`, `ty check`, `openspec validate --specs` (68 passed) and `openspec validate commit-oracle-transfer-in-bounded-batches --strict`: passed.

### Pending

- Production re-run of the full 4.3-million-row transfer with this change (task 2.3); recorded here before archiving.
