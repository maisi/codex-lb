## ADDED Requirements

### Requirement: SQLite transfer is an explicit offline operation

The database CLI SHALL provide `migrate-to-oracle --source-sqlite PATH` with optional `--source-key-file PATH`, `--batch-size`, and `--dry-run`, using the existing target database URL option or environment. It MUST reject non-Oracle targets and nonpositive batch sizes. It MUST require exclusive access to the stopped SQLite installation for its complete source-read lifetime, coordinate with the existing lifecycle and migration locks, and hold a SQLite write fence against independent writers. It MUST transfer from a private snapshot and MUST NOT upgrade or modify the source database, generate or replace an encryption key, change application configuration, or start the application.

#### Scenario: An installation is still running
- **WHEN** the source installation holds its lifecycle lock or another SQLite writer prevents the source fence
- **THEN** transfer fails before reading a transferable snapshot or modifying the Oracle target
- **AND** the diagnostic instructs the operator to stop every process using the source installation

#### Scenario: An older SQLite installation is transferred
- **WHEN** a supported older SQLite schema is supplied
- **THEN** the command upgrades only its private snapshot through the existing SQLite migration lineage
- **AND** the original SQLite database remains unchanged

### Requirement: SQLite transfer preflight proves complete representability

Transfer SHALL validate source database integrity, foreign keys, supported schema, and the complete application-table inventory after snapshot upgrade. It MUST reject unknown source application tables or incompatible columns rather than omit them. It MUST read the supplied encryption key or the existing sibling `encryption.key`, validate any recorded key fingerprint and encrypted application values, and fail on missing, invalid, or mismatching encryption material without generating a replacement. It MUST validate each value against Oracle storage codecs and bounds before target data changes. Filesystem archives and the encryption key MUST remain filesystem artifacts, and successful transfer MUST identify that the existing data directory or an operator-made copy is required for cutover.

#### Scenario: Source contains data beyond account records
- **WHEN** the SQLite installation includes API keys, settings, usage, logs, conversations, coordination state, and encrypted credentials
- **THEN** all application tables and values participate in preflight and transfer
- **AND** no migration-version ledger is copied to Oracle

#### Scenario: A key or value is incompatible
- **WHEN** an encrypted value cannot be decrypted with the selected key, a key fingerprint disagrees, or a value exceeds Oracle storage bounds
- **THEN** transfer fails before any target data changes
- **AND** output does not contain the value, key, database URL, or credentials

### Requirement: SQLite transfer preserves the Oracle baseline and rejects used targets

Transfer SHALL serialize with Oracle schema migrations through the existing Oracle migration mutex, prepare a fresh dedicated target with the verified Oracle lineage when needed, and accept only an empty target or an exact pristine baseline. Baseline acceptance MUST verify schema and generated seed values while allowing irrelevant generated seed timestamps to differ. A target containing application data, incompatible objects, or changed baseline values MUST be rejected without overwriting that data. SQLite migration-version ledgers MUST NOT replace the Oracle ledger. Required generated-identifier sequences MUST be advanced beyond imported identifiers before the data transaction so sequence DDL cannot commit a partial transfer.

#### Scenario: A used target is selected
- **WHEN** the target contains application rows or changed seed values beyond its pristine baseline
- **THEN** transfer fails without deleting or replacing existing rows

#### Scenario: Imported identifiers exceed fresh sequence values
- **WHEN** source rows contain numeric identifiers larger than the fresh Oracle sequence position
- **THEN** generated identifiers after transfer exceed every imported identifier for that sequence
- **AND** Oracle retains its own verified migration lineage

### Requirement: SQLite transfer commits only completely verified application data

Transfer SHALL discover all application tables from current application metadata, read and write in bounded batches, preserve explicit identifiers and foreign-key relationships, and handle nullable self references without losing their original values. Baseline seed removal, application row copies, self-reference restoration, and verification MUST execute in one Oracle data transaction. Before commit it MUST compare source and target row counts and a complete typed, order-independent digest for every application table. Any pre-commit copy or verification failure MUST roll back all transferred rows and seed changes. Transfer MUST NOT resume or upsert into a used target; a failed attempt MUST permit a fresh attempt against the preserved pristine target. Oracle schema preparation and sequence advancement MAY persist after a failed transfer, and diagnostics MUST explain that limitation without reporting success.

#### Scenario: A later table fails during transfer
- **WHEN** a database or verification failure occurs after earlier tables have been inserted
- **THEN** the transaction rolls back inserted rows and seed changes for every table
- **AND** the target remains eligible for a new transfer when its baseline remains pristine

#### Scenario: Row counts match but a value differs
- **WHEN** source and target have equal table row counts but one persisted value differs
- **THEN** complete row verification fails and prevents commit

### Requirement: SQLite transfer dry run is read-only for both installations

Dry run SHALL execute source snapshot, schema, integrity, key, and Oracle-value preflight and inspect the target read-only. It MUST NOT create or modify Oracle schema, rows, migration ledgers, or sequence positions. It MUST report source table and row counts and whether target preparation is required without claiming that a transfer has occurred. Normal transfer output and failures MUST reveal only operational status, table names, and counts rather than row contents or secrets, and owned locks, connections, engines, and private snapshots MUST be released on success and failure.

#### Scenario: A fresh Oracle schema is inspected with dry run
- **WHEN** dry run is invoked against an otherwise valid empty target
- **THEN** it reports the transfer inventory and required target preparation
- **AND** the target remains empty with no advanced sequences or migration ledger

#### Scenario: Transfer exits unsuccessfully
- **WHEN** validation, database work, or verification fails
- **THEN** the command exits unsuccessfully with a sanitized diagnostic
- **AND** its owned resources and private snapshot are released
