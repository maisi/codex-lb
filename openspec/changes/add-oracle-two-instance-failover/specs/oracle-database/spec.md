## MODIFIED Requirements

### Requirement: Verified single-instance runtime can install and operate

After real-database verification, Oracle application startup SHALL support one application instance using an isolated, explicitly selected application schema. Installation MUST use an immutable Alembic-owned Oracle baseline, MUST preserve unrelated schemas and data, and MUST reject incompatible or partially installed schema rather than stamp unverified live ORM metadata. Repeat upgrades MUST be idempotent. Multi-instance operation MUST follow the separately verified Oracle two-instance failover pilot contract.

#### Scenario: Fresh isolated Oracle installation
- **WHEN** the operator installs and starts one instance against a fresh Oracle application schema
- **THEN** the versioned schema is installed and dashboard settings, accounts, keys, usage and logs persist through the existing application interfaces
- **AND** a subsequent restart uses that schema without deleting application data

## ADDED Requirements

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
