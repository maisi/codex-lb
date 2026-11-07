## Why

Oracle's four-slot background pool can be exhausted by the six-hour Auth Guardian: three workers retain read transactions while nested refresh and claim operations need more connections. The same pool serves leader renewal, so the resulting checkout timeouts cause lease loss and failures throughout background maintenance, including shortly after startup.

## What Changes

- Use existing per-operation accounts repositories for guardian selection, eligibility reads, and owned token refresh, releasing connections before claim waits, admission waits, and OAuth I/O.
- Isolate Oracle leader acquisition, renewal, and release in an automatically managed single-connection pool.
- Include that connection in Oracle capacity checks and deployment guidance, retaining four/zero request and background pool defaults and explicit overrides.
- Cover the scheduler/refresh/lease path with bounded-pool regressions, including slow upstream work, cancellation, and partial failure.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `usage-refresh-policy`: Guardian refresh does not retain sessions across slow waits and preserves cancellation settlement.
- `oracle-database`: Oracle leader coordination has independent connection capacity and capacity calculations include it.

## Impact

Guardian repository wiring, Oracle session lifecycle, leader-election session provider, Oracle budget CLI and HA pool probes, tests, and OpenSpec/deployment context. No new environment setting, schema migration, dependency, or required setup step. Default application capacity changes from eight to nine connections per Oracle replica (18 steady and 27 with one replacement across two replicas).
