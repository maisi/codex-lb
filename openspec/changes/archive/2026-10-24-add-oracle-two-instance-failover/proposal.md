## Why

Oracle single-instance operation is verified, but two application instances have not been exercised together through real networking, process death and restart. The operator approved a first HA sprint where new requests and client retries move to the surviving instance; transparent continuation of an interrupted stream remains a later milestone.

## What Changes

- Add a bounded real-process Oracle failover harness with two independently identified application instances behind a health-aware load balancer and a controlled upstream.
- Verify shared settings, encryption-key consistency, singleton scheduler ownership, token-refresh coordination, request accounting and recovery from interrupted work.
- Exercise hard process loss, client retry, restart and planned drain/replacement, measuring recovery time and the two-pool session budget.
- Fix product defects demonstrated by those paths, and provide CI coverage plus an operator configuration and runbook.
- Record a concrete feasibility assessment for transparent stream continuation without claiming that behavior in this sprint.

## Capabilities

### New Capabilities

### Modified Capabilities

- `oracle-database`: Define the verified two-instance failover milestone and its isolation, accounting and session-budget acceptance criteria.
- `replica-operations`: Extend the shared-database topology contract to the verified Oracle pilot, including client-retry semantics and independent instance endpoints.

## Impact

Oracle integration tests and CI, targeted coordination/recovery paths where failures are demonstrated, deployment examples and OpenSpec-linked documentation. SQLite remains single-process. This sprint does not provide database failover, seamless streaming takeover or automatic migration of existing database contents.
