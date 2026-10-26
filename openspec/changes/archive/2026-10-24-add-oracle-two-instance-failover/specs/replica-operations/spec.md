## RENAMED Requirements

- FROM: `### Requirement: Multi-replica deployments require shared PostgreSQL coordination`
- TO: `### Requirement: Multi-replica deployments require shared database coordination`

## MODIFIED Requirements

### Requirement: Multi-replica deployments require shared database coordination

Running more than one application replica SHALL require a shared PostgreSQL database or the verified Oracle two-instance pilot through which all cross-replica coordination flows (`scheduler_leader`, `bridge_ring_members`, `http_bridge_sessions`, `cache_invalidation`, `sticky_sessions`, `runtime_sentinels`); leader election enabled (`CODEX_LB_LEADER_ELECTION_ENABLED`, default `true`); a unique instance id and reachable replica-specific advertise URL per replica; and identical encryption key material mounted on every replica. Each pilot instance MUST use one application worker. Explicitly disabling leader election MUST remain a single-instance escape hatch and MUST NOT be used with multiple replicas. Oracle support MUST retain its documented process-failover and client-retry acceptance boundaries.

#### Scenario: Supported two-replica topology
- **GIVEN** two replicas configured with the same supported shared database
- **AND** leader election is enabled on both
- **AND** each replica has a unique bridge instance id and reachable advertise URL
- **AND** both replicas mount the same encryption key
- **WHEN** both replicas start
- **THEN** exactly one replica acquires the scheduler leader lease and runs singleton schedulers
- **AND** hard-continuity requests reaching a non-owner are forwarded to the owner

#### Scenario: Leader election left at its default preserves the singleton guarantee
- **GIVEN** two replicas sharing one supported database
- **AND** leader election is left enabled
- **WHEN** both replicas start
- **THEN** exactly one replica acquires the lease and runs singleton schedulers
- **AND** the operator observes no duplicate upstream polling (usage refresh, automations, retention)
- **AND** explicitly disabling leader election would make each replica act as leader, run singleton schedulers N-fold, and is unsupported for this topology

### Requirement: SQLite deployments are single-process

SQLite database backends SHALL be operated with exactly one application process; multi-process and multi-replica SQLite deployments — including `uvicorn --workers N` and sharing one SQLite file over a network volume — are unsupported. On SQLite the leader lease is NOT bypassed: it is arbitrated in the database through the same atomic conditional upsert used on PostgreSQL, so when more than one process is pointed at one SQLite file exactly one process wins the lease and the others observe rowcount 0 and remain followers. Multi-process SQLite remains unsupported for other reasons (single-writer contention), and the database rate limiter's cross-process atomicity is likewise unaffected.

#### Scenario: Two leader elections over one SQLite file arbitrate in the database

- **GIVEN** two `LeaderElection` instances pointed at the same SQLite database
- **WHEN** both attempt to acquire the leader lease while no unexpired lease exists
- **THEN** exactly one acquisition wins the lease
- **AND** the other observes rowcount 0 and remains a follower because SQLite arbitrates the lease in the database rather than bypassing it

#### Scenario: Operator scales a SQLite deployment

- **GIVEN** a deployment using a SQLite `CODEX_LB_DATABASE_URL`
- **WHEN** the operator wants more than one application process or replica
- **THEN** the supported path is migrating to a shared PostgreSQL database or the verified Oracle two-instance pilot
