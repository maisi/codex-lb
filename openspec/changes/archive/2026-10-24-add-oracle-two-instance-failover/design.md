## Context

See proposal.md. The parent Oracle PR is still open, so this is a focused stacked PR on that branch. Native Oracle leader, refresh, file-pin, cache and key-agreement primitives already have database concurrency tests. Existing multi-replica tests mostly share one Python process and do not establish process-loss acceptance.

## Goals / Non-Goals

**Goals:** independent real application runtimes, observable shared coordination and accounting, a reproducible readiness-aware front door, bounded crash/restart/drain tests and an operator example.

**Non-Goals:** replacing the upstream service, seamless stream migration, replaying an uncertain completed upstream request, refunding unknown usage early, database redundancy or deploying onto unspecified external hosts.

## Decisions

- Use two separate single-worker application processes with independent local data directories and the same mounted encryption key, real Oracle pools and TCP listeners. A third process exercises update overlap.
- Use HAProxy for routing and readiness checks, with automatic request replay disabled. A custom Python test proxy would not prove compatibility with an operator's standard load balancer.
- Keep fake upstream behavior and observations inside test-only worker/support code. Normal application APIs, migration, coordination, reservations and settlement remain real. A controlled upstream is necessary to kill a process during a reproducible in-flight request without sending synthetic credentials outside the test environment.
- Use an explicitly selected empty HA schema, separate from the persistent application and other migration tests. Refuse pre-existing tables. Capture bounded per-process logs and redact secrets before displaying a failure. Always reap owned processes, even after partial startup.
- Preserve the existing reservation policy: stale reservations are reclaimed after six hours of lost heartbeat, with a 24-hour hard ceiling. Test accelerated cutoffs explicitly rather than changing production defaults or claiming immediate refunds after uncertain upstream execution.
- Record routing, leader-transfer and readiness timings as measured acceptance evidence. Application pools retain four connections and zero overflow each, yielding sixteen normal and twenty-four overlap application sessions; migrations need separate headroom.
- Introduce no new production settings. Test-only controls are confined to the standalone test worker. The operator example uses existing database, instance, key, advertise and leader settings.

## Risks / Trade-offs

- Owner leases can delay a same-session retry; tests must distinguish a new request from protected continuity ownership and preserve account fences.
- Killing a process can leave an unknown upstream outcome; no automatic replay or exactly-once upstream guarantee is added.
- The Free database and front load balancer remain shared dependencies. Two processes on one test machine simulate process loss, not independent physical-host or network-partition availability.
- Additional cold schema writes can be slow on Free; installation uses the production migration timeout and the overall HA test has a bounded explicit deadline.

## Migration Plan

No schema migration is planned. Reuse the parent immutable Oracle baseline. Provision the shared application user and secret mounts, start one worker per instance, validate individual readiness, then enable the load-balancer backends. Roll back by draining/removing the second backend while keeping the original shared database and key.
