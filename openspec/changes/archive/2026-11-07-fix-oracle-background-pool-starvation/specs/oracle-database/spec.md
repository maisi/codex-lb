## MODIFIED Requirements

### Requirement: Oracle Free connection budgets include both pools and replica overlap

The Oracle preparation check SHALL calculate application session demand from both configurable application pools, one fixed leader-coordination connection per replica, configured pool size, maximum overflow, intended replicas, and explicitly supplied update-overlap replicas. It MUST reject invalid counts and MUST report when application demand leaves no room within the supplied session limit. The default session limit SHALL be 30 for the Always Free preparation scenario. It MUST NOT represent that budget as a measured throughput guarantee.

#### Scenario: Two instances leave room for operations
- **WHEN** pool size is four, overflow is zero, replica count is two, and update overlap is one extra replica
- **THEN** the check reports 18 steady-state and 27 update-overlap application sessions
- **AND** it reports three sessions remaining under the limit of 30 during the overlap

#### Scenario: Oversized connection budget
- **WHEN** the application session demand including leader coordination is greater than or equal to the configured session limit
- **THEN** the check reports an unsuccessful preparation result naming the pool and replica budget

### Requirement: Oracle defaults fit a single Free instance

When Oracle is selected and the existing pool settings are not explicitly supplied, the request and background pools SHALL each default to size four with zero overflow. The leader-coordination pool SHALL use one connection with zero overflow. Explicit existing settings MUST remain authoritative for the request and background pools, and an exhausted 30-session budget MUST fail before connecting. Other database backends MUST retain their existing defaults.

#### Scenario: Oracle is selected without pool overrides
- **WHEN** the application uses an Oracle URL with no explicit pool size or overflow
- **THEN** the request and background pools each use four connections with zero overflow
- **AND** the leader pool uses one connection with zero overflow, making nine application sessions per replica

### Requirement: Oracle failover verification uses real processes and bounded resources

Two-instance acceptance MUST exercise real application processes over TCP through a standard readiness-aware load balancer, hard process termination, restart and planned draining. The test harness MUST refuse a nonempty schema, redact connection secrets, bound process startup and teardown, and terminate every owned child on failure. Default application demand including leader coordination MUST remain at most eighteen sessions for two processes and twenty-seven for a three-process update overlap, excluding documented migration and administrative connections. External upstream responses MAY be controlled for deterministic verification.

#### Scenario: An application process is drained for replacement
- **WHEN** the operator starts draining one process while its peer remains ready
- **THEN** the draining process becomes unready for new traffic
- **AND** the peer continues serving new requests while accepted work finishes within the existing shutdown budget
- **AND** a replacement process can become ready without exceeding the configured application session budget

#### Scenario: A test target already contains tables
- **WHEN** the failover harness is pointed at a nonempty schema
- **THEN** it fails before creating, dropping or altering application objects

## ADDED Requirements

### Requirement: Oracle leader coordination has independent connection capacity

Oracle scheduler lease acquisition, renewal, and release MUST use an independently pooled single connection with zero overflow, unavailable to request and background jobs. This isolation MUST apply automatically without a new setting. Startup and shutdown MUST own and dispose that pool. SQLite and PostgreSQL MUST preserve their existing session and connection-budget behavior.

#### Scenario: Background jobs exhaust their pool

- **GIVEN** every Oracle background pool connection is checked out by background work
- **WHEN** a scheduler lease is acquired, renewed, or released
- **THEN** the lease operation can complete without waiting for a background connection to be returned

#### Scenario: Application shuts down

- **WHEN** the application closes its database engines
- **THEN** the leader-coordination engine is also disposed

#### Scenario: Another backend is selected

- **WHEN** SQLite or PostgreSQL initializes its background database
- **THEN** no separate leader-coordination pool is created
