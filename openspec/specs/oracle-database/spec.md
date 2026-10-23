# oracle-database Specification

## Purpose

Define safe preparation and validation of an Oracle Autonomous Database backend before full application and two-instance support is enabled.

## Requirements

### Requirement: Oracle connection validation is read-only and explicit

The database CLI SHALL provide an explicitly invoked Oracle connectivity check. It MUST validate an Oracle Thin connection without creating, updating, deleting, or stamping application schema or rows. It MUST close owned connections and engines on success and failure, and MUST NOT expose passwords or wallet secrets in output. A successful check MUST distinguish connectivity from application compatibility.

#### Scenario: Successful Oracle preparation check
- **WHEN** an operator invokes the Oracle check with a reachable Oracle database
- **THEN** the command reports connectivity and server information without modifying application data
- **AND** it states that Oracle application runtime support is not yet verified

#### Scenario: Invalid or failed connection
- **WHEN** the supplied URL is not an Oracle URL, the Oracle driver is absent, or connection establishment fails
- **THEN** the command exits unsuccessfully with actionable diagnostics that do not include credentials
- **AND** owned resources are released

### Requirement: Oracle Free connection budgets include both pools and replica overlap

The Oracle preparation check SHALL calculate application session demand from both application pools, configured pool size, maximum overflow, intended replicas, and explicitly supplied update-overlap replicas. It MUST reject invalid counts and MUST report when application demand leaves no room within the supplied session limit. The default session limit SHALL be 30 for the Always Free preparation scenario. It MUST NOT represent that budget as a measured throughput guarantee.

#### Scenario: Two instances leave room for operations
- **WHEN** pool size is four, overflow is zero, replica count is two, and update overlap is one extra replica
- **THEN** the check reports 16 steady-state and 24 update-overlap application sessions
- **AND** it reports six sessions remaining under the limit of 30 during the overlap

#### Scenario: Oversized connection budget
- **WHEN** the application session demand is greater than or equal to the configured session limit
- **THEN** the check reports an unsuccessful preparation result naming the pool and replica budget

### Requirement: Incomplete Oracle support cannot mutate schema or start the application

Until Oracle migrations and runtime coordination are implemented and verified, application startup and schema-mutating database commands targeting Oracle MUST stop with an explicit unsupported-backend error before opening a database connection or performing schema mutation. The Oracle preparation command SHALL remain available. SQLite and PostgreSQL SHALL preserve their current startup and migration behavior.

#### Scenario: Oracle startup or migration is attempted
- **WHEN** an operator selects an Oracle database for application startup or a schema-mutating command
- **THEN** the operation fails before database connection or mutation
- **AND** the diagnostic identifies the preparation command and incomplete support boundary

### Requirement: Oracle schema preparation preserves existing storage behavior

Oracle-specific schema representations MUST preserve subsecond timestamp precision, automatic generation of numeric identifiers, fixed hash equality, and the semantic uniqueness conditions of existing records. SQLite and PostgreSQL schema representations MUST remain unchanged. Any unresolved Oracle representation MUST remain an explicit blocker to enabling the backend.

#### Scenario: Existing backend schema is rendered
- **WHEN** SQLite or PostgreSQL schema statements are generated after Oracle-specific type preparation
- **THEN** their existing column and index behavior is preserved

#### Scenario: Oracle schema representations are inspected
- **WHEN** an Oracle-prepared timestamp, generated identifier, or fixed binary hash is rendered
- **THEN** it retains the precision, generation, and equality behavior required by the corresponding application value

### Requirement: Oracle schema inventory is available without a database

The database CLI SHALL provide an offline Oracle schema inventory command that reports model table counts and unresolved Oracle representation blockers, including unbounded strings, filtered index semantics, and empty-string semantics. It MUST support structured JSON output, MUST exit unsuccessfully while blockers remain, and MUST NOT open a database connection or require the optional Oracle driver. It MUST identify the report as preparation rather than application readiness.

#### Scenario: Schema blockers are inspected offline
- **WHEN** an operator invokes the Oracle schema inventory with Oracle selected in the environment
- **THEN** the command reports blocker counts and exits unsuccessfully without opening a database connection
- **AND** structured output identifies each blocker by kind, table, and object

### Requirement: Prepared Oracle migration mutex spans schema transactions

An explicitly invoked Oracle migration mutex SHALL serialize processes sharing the same database for the complete migration sequence, including work committed on other connections. Waiting MUST be bounded by the existing migration lock timeout. The mutex MUST release its owned connection on body failure, timeout, and normal completion. Missing database package privileges MUST fail explicitly without falling back to an unlocked migration. This primitive MUST NOT enable unsupported Oracle application startup or migrations.

#### Scenario: A second migration owner waits
- **GIVEN** one process holds the Oracle migration mutex
- **WHEN** another process attempts the same mutex
- **THEN** only one process enters the protected section at a time
- **AND** commits by other schema connections do not release the mutex

#### Scenario: Oracle mutex privileges are unavailable
- **WHEN** the database user cannot execute the required locking package
- **THEN** mutex acquisition fails with actionable permission guidance
- **AND** the protected migration body does not execute

### Requirement: Prepared Oracle file ownership cannot cross accounts

Oracle file-ownership operations, when invoked against a prepared test schema, MUST grant a live file pin to at most one account across concurrent database sessions. An existing owner MUST be able to refresh its own pin. Another account MUST be rejected while the pin is live and MUST be able to take over after expiry. Pin TTL decisions MUST use database time after any row-lock wait, and failures MUST release the caller's transaction. These operations MUST NOT enable unsupported Oracle application startup.

#### Scenario: Two accounts race for one file
- **WHEN** independent Oracle sessions claim the same previously unowned file for different accounts
- **THEN** exactly one account becomes the live owner
- **AND** the other receives an ownership conflict without changing that owner

#### Scenario: Expired ownership is replaced
- **GIVEN** an Oracle file pin has expired according to database time
- **WHEN** a different account claims that file
- **THEN** it becomes the live owner with a full TTL measured after any lock wait

### Requirement: Prepared Oracle leader leases preserve exclusive ownership

Oracle leader coordination against a prepared test schema MUST grant an unexpired scheduler lease to at most one distinct leader. Acquisition and renewal MUST evaluate expiry on the database clock after any row-lock wait. Renewal MUST NOT resurrect an expired lease, and a definitive non-owner result MUST demote the caller. The returned remaining lifetime MUST be measured in the database before commit and anchored to the caller's monotonic clock. Prepared coordination MUST NOT enable unsupported Oracle application startup.

#### Scenario: Concurrent initial leader acquisition
- **WHEN** two leaders independently acquire the same absent Oracle scheduler lease
- **THEN** exactly one becomes the leader and the other remains a follower

#### Scenario: A renewal waits past lease expiry
- **GIVEN** a renewal waits behind a row lock until its lease expires
- **WHEN** it can continue
- **THEN** the lease is not renewed and the instance relinquishes leadership
