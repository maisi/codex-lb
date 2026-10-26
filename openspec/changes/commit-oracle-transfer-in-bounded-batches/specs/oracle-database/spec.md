## MODIFIED Requirements

### Requirement: SQLite transfer preserves the Oracle baseline and rejects used targets

Transfer SHALL serialize with Oracle schema migrations through the existing Oracle migration mutex, prepare a fresh dedicated target with the verified Oracle lineage when needed, and accept only an empty target, an exact pristine baseline, or a target carrying the incomplete-transfer marker of an interrupted transfer. Baseline acceptance MUST verify schema and generated seed values while allowing irrelevant generated seed timestamps to differ. A target containing application data, incompatible objects, or changed baseline values without that marker MUST be rejected without overwriting that data. SQLite migration-version ledgers MUST NOT replace the Oracle ledger. Required generated-identifier sequences MUST be advanced beyond imported identifiers before the first data batch.

#### Scenario: A used target is selected
- **WHEN** the target contains application rows or changed seed values beyond its pristine baseline and carries no incomplete-transfer marker
- **THEN** transfer fails without deleting or replacing existing rows

#### Scenario: Imported identifiers exceed fresh sequence values
- **WHEN** source rows contain numeric identifiers larger than the fresh Oracle sequence position
- **THEN** generated identifiers after transfer exceed every imported identifier for that sequence
- **AND** Oracle retains its own verified migration lineage

### Requirement: SQLite transfer commits only completely verified application data

Transfer SHALL discover all application tables from current application metadata, read and write in bounded batches, preserve explicit identifiers and foreign-key relationships, and handle nullable self references without losing their original values. Before the first data batch it MUST commit an `oracle_transfer_incomplete` row in `runtime_sentinels` in the same transaction that verified the target and held the target table locks. Each seed-removal, row-copy and self-reference-restoration batch MUST then commit separately so that Oracle undo use is bounded by the batch size rather than the installation size. After each table it MUST compare source and target row counts and a complete typed, order-independent digest, excluding only the marker row. The marker MUST be removed only in a final transaction after every table verified, and success MUST NOT be reported before that commit. Transfer MUST NOT resume or upsert: a repeated transfer against a marked target MUST delete every application row except the marker in committed bounded batches and copy every table again. Oracle schema preparation and sequence advancement MAY persist after a failed transfer, and diagnostics MUST explain that limitation without reporting success.

#### Scenario: A later table fails during transfer
- **WHEN** a database or verification failure occurs after earlier batches committed
- **THEN** the command fails without reporting success and the target keeps the incomplete-transfer marker
- **AND** the diagnostic states that application startup is refused and that repeating the transfer restarts from a cleared target

#### Scenario: An interrupted transfer is repeated
- **WHEN** transfer runs again against a target carrying the marker from an interrupted attempt
- **THEN** previously committed rows are removed in bounded batches and every table is copied and verified again
- **AND** after success the target equals the source and the marker is absent

#### Scenario: Row counts match but a value differs
- **WHEN** source and target have equal table row counts but one persisted value differs
- **THEN** complete row verification fails and the marker remains

#### Scenario: An installation exceeds the Oracle undo capacity of one transaction
- **WHEN** the source contains more rows than one Oracle transaction can hold in undo
- **THEN** no single transfer transaction contains more than one bounded batch of row changes

### Requirement: SQLite transfer dry run is read-only for both installations

Dry run SHALL execute source snapshot, schema, integrity, key, and Oracle-value preflight and inspect the target read-only. It MUST NOT create or modify Oracle schema, rows, migration ledgers, or sequence positions. It MUST report source table and row counts, whether target preparation is required, and whether the target carries an incomplete-transfer marker, without claiming that a transfer has occurred. Normal transfer output and failures MUST reveal only operational status, table names, and counts rather than row contents or secrets, and owned locks, connections, engines, and private snapshots MUST be released on success and failure.

#### Scenario: A fresh Oracle schema is inspected with dry run
- **WHEN** dry run is invoked against an otherwise valid empty target
- **THEN** it reports the transfer inventory and required target preparation
- **AND** the target remains empty with no advanced sequences or migration ledger

#### Scenario: An interrupted target is inspected with dry run
- **WHEN** dry run is invoked against a target carrying the incomplete-transfer marker
- **THEN** it succeeds, reports the marker, and leaves every committed row unchanged

#### Scenario: Transfer exits unsuccessfully
- **WHEN** validation, database work, or verification fails
- **THEN** the command exits unsuccessfully with a sanitized diagnostic
- **AND** its owned resources and private snapshot are released

## ADDED Requirements

### Requirement: Application startup refuses an incompletely transferred Oracle database

Application startup against Oracle MUST check `runtime_sentinels` for the `oracle_transfer_incomplete` marker after database initialization and before the encryption-key fingerprint is stamped. When the marker is present, startup MUST fail with a diagnostic naming the interrupted transfer and the restart command, and MUST NOT serve requests. Other database backends MUST NOT perform this check.

#### Scenario: The application starts against a partially transferred target
- **WHEN** the configured Oracle database carries the incomplete-transfer marker
- **THEN** startup fails before stamping the encryption-key fingerprint or serving traffic
