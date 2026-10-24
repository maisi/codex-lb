# oracle-database Specification

## Purpose

Define installation, storage, connection validation and operation of Oracle Autonomous Database application instances, including the verified two-instance process-failover pilot.

## Requirements

### Requirement: Oracle connection validation is read-only and explicit

The database CLI SHALL provide an explicitly invoked Oracle connectivity check. It MUST validate an Oracle Thin connection without creating, updating, deleting, or stamping application schema or rows. It MUST close owned connections and engines on success and failure, and MUST NOT expose passwords or wallet secrets in output. A successful check MUST distinguish connectivity from application compatibility.

#### Scenario: Successful Oracle preparation check
- **WHEN** an operator invokes the Oracle check with a reachable Oracle database
- **THEN** the command reports connectivity and server information without modifying application data
- **AND** it states that the check establishes connectivity only and does not verify application or HA readiness

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

### Requirement: Oracle runtime uses its verified driver and migration lineage

Oracle application startup SHALL use the native oracle+oracledb Thin driver. Unsupported Oracle driver variants MUST fail before loading a database driver and MUST NOT expose credentials. Oracle installation MUST use its dedicated Alembic lineage, MUST reject manual stamping that bypasses baseline verification, and MUST reject replaying the SQLite/PostgreSQL migration history. SQLite and PostgreSQL SHALL preserve their existing behavior.

#### Scenario: Unsupported Oracle driver is selected
- **WHEN** an operator selects an Oracle driver other than oracle+oracledb
- **THEN** startup fails before creating an engine with guidance naming the native Thin driver
- **AND** its diagnostic omits database and wallet credentials

#### Scenario: Oracle baseline verification is bypassed
- **WHEN** an operator attempts to stamp an Oracle schema or replay the SQLite/PostgreSQL migration history
- **THEN** the operation fails before opening a database connection
- **AND** it identifies the dedicated Oracle upgrade command

### Requirement: Oracle schema preparation preserves existing storage behavior

Oracle-specific schema representations MUST preserve subsecond timestamp precision, automatic generation of numeric identifiers, fixed hash equality, and the semantic uniqueness conditions of existing records. SQLite and PostgreSQL schema representations MUST remain unchanged. Any unresolved Oracle representation MUST remain an explicit blocker to enabling the backend.

#### Scenario: Existing backend schema is rendered
- **WHEN** SQLite or PostgreSQL schema statements are generated after Oracle-specific type preparation
- **THEN** their existing column and index behavior is preserved

#### Scenario: Oracle schema representations are inspected
- **WHEN** an Oracle-prepared timestamp, generated identifier, or fixed binary hash is rendered
- **THEN** it retains the precision, generation, and equality behavior required by the corresponding application value

### Requirement: Oracle schema inventory is available without a database

The database CLI SHALL provide an offline Oracle schema inventory command that reports model table counts and unresolved Oracle representation blockers, including unbounded strings, filtered index semantics, and empty-string semantics. It MUST support structured JSON output, MUST exit unsuccessfully while blockers remain, and MUST NOT open a database connection or require the optional Oracle driver. It MUST identify the report as an offline schema inventory rather than application readiness.

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

### Requirement: Prepared Oracle refresh claims preserve token ownership

Oracle refresh claims against a prepared test schema MUST allow at most one distinct claimant/refresh-owner pair to hold an unexpired account claim. Re-entry by the same pair MUST remain allowed, while another refresh owner from the same process MUST remain excluded. Acquisition and expiry MUST use database UTC time after any row-lock wait. Release MUST affect only the exact claimant/owner pair and MUST leave foreign claims intact. Claim acquisition MUST commit before returning so upstream token exchange does not hold a database transaction or row lock. Prepared claims MUST NOT enable unsupported Oracle application startup.

#### Scenario: Concurrent token refresh ownership
- **WHEN** independent Oracle sessions claim one account for different refresh-owner pairs
- **THEN** exactly one pair acquires the claim and the other cannot exchange under that claim

#### Scenario: A different owner attempts release
- **GIVEN** an unexpired account claim belongs to one refresh-owner pair
- **WHEN** another pair releases the account claim
- **THEN** the original claim remains intact

### Requirement: Prepared Oracle cache invalidation increments shared versions atomically

Each committed Oracle cache invalidation transaction against a prepared test schema MUST atomically increment its namespace version by one, including concurrent first insertion. Rolled-back transactions MUST NOT leave partial increments. Retrying an uncertain commit MAY produce a redundant bump and MUST preserve peer invalidation delivery. Existing peer pollers MUST observe committed version changes through their normal callback path, and local acknowledgement MUST preserve peer delivery. Prepared invalidation MUST NOT enable unsupported Oracle application startup.

#### Scenario: Concurrent first namespace changes
- **WHEN** independent Oracle sessions successfully bump one previously absent namespace
- **THEN** the committed version includes every successful bump
- **AND** a duplicate-key insertion race does not discard a bump

#### Scenario: A cache bump transaction fails
- **WHEN** a bump fails before commit
- **THEN** it leaves no partial version change
- **AND** a later successful bump remains possible

#### Scenario: A committed bump acknowledgement is lost
- **WHEN** a bump commits but its caller receives a retryable commit error
- **THEN** retry may increment the version again
- **AND** peers still reconcile the committed change without treating version numbers as event counts

#### Scenario: A peer observes a committed change
- **GIVEN** a peer poller has recorded its current version baseline
- **WHEN** another poller successfully bumps a namespace
- **THEN** the peer invokes its registered invalidation callback on observing the new version

### Requirement: Prepared Oracle startup fingerprint stamping preserves the first key

Oracle encryption-key fingerprint verification against a prepared test schema MUST atomically preserve the first committed fingerprint. Concurrent replicas using the same key MUST both verify successfully. Concurrent replicas using different keys MUST establish one stored fingerprint and reject the nonmatching replica in enforce mode. Existing warn and off mode semantics MUST remain unchanged. Prepared verification MUST NOT enable unsupported Oracle application startup.

#### Scenario: Concurrent replicas agree on the encryption key
- **WHEN** independent Oracle sessions verify the same key against an empty sentinel table
- **THEN** both verifications succeed and one matching sentinel exists

#### Scenario: Concurrent replicas disagree on the encryption key
- **WHEN** independent Oracle sessions verify different keys against an empty sentinel table in enforce mode
- **THEN** one verification succeeds and the other reports an encryption-key mismatch
- **AND** the mismatching replica does not overwrite the stored fingerprint

#### Scenario: Existing fingerprint mismatch modes are selected
- **GIVEN** an Oracle sentinel belongs to another encryption key
- **WHEN** verification uses warn mode
- **THEN** it logs the mismatch and preserves the sentinel
- **AND** off mode skips database verification


### Requirement: Verified single-instance runtime can install and operate

After real-database verification, Oracle application startup SHALL support one application instance using an isolated, explicitly selected application schema. Installation MUST use an immutable Alembic-owned Oracle baseline, MUST preserve unrelated schemas and data, and MUST reject incompatible or partially installed schema rather than stamp unverified live ORM metadata. Repeat upgrades MUST be idempotent. Multi-instance operation MUST follow the separately verified Oracle two-instance failover pilot contract.

#### Scenario: Fresh isolated Oracle installation
- **WHEN** the operator installs and starts one instance against a fresh Oracle application schema
- **THEN** the versioned schema is installed and dashboard settings, accounts, keys, usage and logs persist through the existing application interfaces
- **AND** a subsequent restart uses that schema without deleting application data

### Requirement: Oracle runtime storage and lifecycle preserve application contracts

Oracle runtime SHALL preserve distinct empty-string and NULL values, timestamp microseconds and UTC semantics, generated identifiers, and conditional uniqueness. Request and background pools MUST initialize each physical connection in UTC, use bounded connection budgets compatible with the Free database, and release or invalidate connections on errors and cancellation within a documented bound. SQLite and PostgreSQL behavior MUST remain unchanged.

#### Scenario: Oracle session defaults differ from UTC
- **WHEN** a new runtime connection inherits a non-UTC session timezone
- **THEN** pool initialization sets that connection to UTC before application statements execute
- **AND** persisted and queried application timestamps retain their UTC meaning

#### Scenario: A request is canceled during a database operation
- **WHEN** an Oracle request is canceled while waiting for database work
- **THEN** the application bounds cleanup and prevents reuse of an in-flight connection
- **AND** subsequent requests can obtain a usable connection

### Requirement: Oracle bridge maintenance preserves bounded ownership fences

Oracle bridge retention and abandonment scans SHALL select and lock eligible operations in bounded batches using SQL supported by Oracle Free and Autonomous. Retention MUST delete at most the requested number of operations, MUST preserve nonterminal operations while their owning session has a live owner lease, and MUST recheck eligibility before deleting selected operations.

#### Scenario: Old operations include a live nonterminal operation
- **GIVEN** old terminal operations and an old nonterminal operation whose owner lease is live
- **WHEN** Oracle retention processes a limited batch
- **THEN** it deletes at most that many eligible operations
- **AND** the live nonterminal operation remains until its owner becomes stale


### Requirement: Oracle defaults fit a single Free instance

When Oracle is selected and the existing pool settings are not explicitly supplied, each runtime pool SHALL default to size four with zero overflow. Explicit existing settings MUST remain authoritative and an exhausted 30-session budget MUST fail before connecting. Other database backends MUST retain their existing defaults.

#### Scenario: Oracle is selected without pool overrides
- **WHEN** the application uses an Oracle URL with no explicit pool size or overflow
- **THEN** the request and background pools each use four connections with zero overflow
- **AND** their combined maximum is eight application sessions

### Requirement: Oracle string bounds are explicit and lossless

Previously unbounded Oracle identifier and dimension columns SHALL permit at most 1024 UTF-8 storage bytes, including codec escapes. Oversized values MUST fail without truncation. Existing bounded character fields MUST reserve their supported Unicode width. Free-form text and long URLs MUST remain CLOB values with full-value equality and distinct empty-string/NULL storage.

#### Scenario: A stored CLOB shares an indexed prefix
- **WHEN** two values share the indexed CLOB prefix but differ later
- **THEN** equality lookup distinguishes their complete values
- **AND** prefix index collisions do not establish equality

### Requirement: Oracle two-instance failover preserves request and coordination ownership

The Oracle pilot SHALL support two independently identified single-worker application processes sharing an isolated application schema and encryption key behind a readiness-aware load balancer. New requests and client retries MUST be serviceable by the surviving process after a peer process fails. Singleton work and token refresh MUST retain exclusive database ownership. Completed requests MUST persist their usage exactly once through the existing settlement path. An interrupted request MUST retain the existing conservative reservation and ownership expiry rules rather than being blindly replayed or refunded.

#### Scenario: One process dies during traffic
- **GIVEN** two ready application processes share an Oracle schema
- **WHEN** one process is killed during an active request
- **THEN** the load balancer removes that process from eligible backends
- **AND** a client retry succeeds through the surviving process
- **AND** surviving requests persist their own usage without corrupting the interrupted request's reservation

#### Scenario: A former owner returns
- **WHEN** a failed process is restarted after its ownership has expired or been replaced
- **THEN** it joins with a new process epoch and cannot renew or settle work under a stale owner fence
- **AND** both processes continue serving requests with shared authoritative settings

#### Scenario: The scheduler leader fails
- **WHEN** the process holding the scheduler lease dies
- **THEN** its peer can acquire the lease after expiry
- **AND** only the current lease owner runs protected singleton work

### Requirement: Oracle failover verification uses real processes and bounded resources

Two-instance acceptance MUST exercise real application processes over TCP through a standard readiness-aware load balancer, hard process termination, restart and planned draining. The test harness MUST refuse a nonempty schema, redact connection secrets, bound process startup and teardown, and terminate every owned child on failure. Default application demand MUST remain at most sixteen sessions for two processes and twenty-four for a three-process update overlap, excluding documented migration and administrative connections. External upstream responses MAY be controlled for deterministic verification.

#### Scenario: An application process is drained for replacement
- **WHEN** the operator starts draining one process while its peer remains ready
- **THEN** the draining process becomes unready for new traffic
- **AND** the peer continues serving new requests while accepted work finishes within the existing shutdown budget
- **AND** a replacement process can become ready without exceeding the configured application session budget

#### Scenario: A test target already contains tables
- **WHEN** the failover harness is pointed at a nonempty schema
- **THEN** it fails before creating, dropping or altering application objects

### Requirement: Oracle pilot does not promise transparent stream takeover

An active client stream MAY terminate when its serving process fails. The pilot MUST NOT promise transparent continuation, exactly-once upstream execution, database failover or load-balancer failover. Operators MUST be told that retry eligibility can depend on existing owner leases and that the shared Free database remains a common dependency.

#### Scenario: A stream loses its serving process
- **WHEN** the serving process dies after stream bytes have been delivered
- **THEN** the client can observe an interrupted response
- **AND** recovery uses the documented client-retry path after applicable ownership checks
