# SQLite to Oracle transfer verification

## Completeness and correctness

All five added requirements have implementation and regression coverage:

| Contract | Implementation | Coverage |
| --- | --- | --- |
| Explicit offline source and private upgrade | `app/db/oracle_transfer.py` source snapshot/fences; `app/db/migrate.py` CLI | Live-process/writer refusal, source byte preservation, snapshot-only older-schema upgrade, complete CLI transfer |
| Complete representability and encryption preflight | Source schema/integrity/FK checks and typed Oracle bind validation | Every metadata table populated; missing/invalid/wrong keys, fingerprint/ciphertext mismatch, unknown/ahead schema, broken FK, oversized identifier and RAW hash |
| Pristine target and Oracle lineage | `app/db/oracle_transfer_target.py` seed/schema checks and sequence preparation | Changed settings/application rows rejected, generated seed timestamps tolerated, Oracle ledger retained; real sequence behavior covered by optional Oracle integration |
| Atomic complete verified copy | Bounded typed copy, two-pass nullable self-reference restoration, counts and order-independent typed SHA-256 row aggregation | All 68 tables, actual ciphertext, cycles, NULL/empty/Unicode/CLOB/binary/microsecond fidelity, reversed row order, injected insertion/corruption failures, successful retry after rollback |
| Read-only dry run and resource cleanup | Target inspection before schema/data/sequence changes; context-owned locks/engines/snapshot | Dry-run target-write rejection, released source lock and repeated transfers after failures; safe error and status output |

Copy tests use a real migrated SQLite source and a real relational target with only Oracle-specific connection/schema/sequence/locking seams replaced. The Oracle integration test exercises the actual destination, codecs, migration ledger and subsequent sequence-generated insert when a disposable schema is configured. Existing Oracle CI includes it through `tests/integration/test_oracle*.py`.

## Executed checks

- Existing migration/Oracle baseline/Oracle schema CLI unit suites: **97 passed**.
- New transfer suite: **22 passed, 1 skipped**; additional storage-bound/order cases and updated rollback/retry cases: **5 passed** (three additional unique cases). Total: **122 distinct passing tests**.
- `make lint`: passed, including architecture/settings/migration-topology ratchets and repository-wide Ruff checks/formatting.
- Repository-wide `ty check`: passed.
- Strict change validation: passed.
- Synced main `oracle-database` specification strict validation: passed.
- Global `openspec validate --specs` and strict validation: **50 passed, 18 failed**. Every failed spec file is unchanged from `HEAD`; all failures are pre-existing requirement paragraphs without SHALL/MUST. This change does not modify those capabilities.

## Coherence and acceptance limits

The implementation follows the offline snapshot, metadata inventory, pristine-only destination, separate DDL preparation, atomic DML and same-key/data-volume decisions. SQLite ledgers and deliberately retired columns are not application tables/fields in the Oracle schema. No migration revision, environment variable, runtime default, dashboard UI or optional dependency was added.

`CODEX_LB_TEST_ORACLE_BASELINE_URL` is unset in this workspace. The destructive real-Oracle integration test was therefore skipped, and this change does **not** claim a live Oracle migration has been accepted here. An operator must run dry-run/transfer and application acceptance on their own isolated target before production cutover. Filesystem key/archive continuity remains explicitly required; this tool does not move those files into Oracle. Schema preparation and sequence gaps can survive failure; an uncertain commit is never automatically retried.
