## Why

Upstream has advanced 58 commits to v1.25.0-beta.5 and contains lifecycle, routing, native transport and dashboard improvements. Issue #27 remains unresolved: a temporary continuity-owner rate limit strands an otherwise recoverable Responses session despite another eligible account.

## What Changes

- Merge upstream through `5794d8d7` while preserving fork-only vending, ranking, continuation, reports, warmup and publishing behavior.
- Recover temporary owner-unavailable continuations across compatible accounts when the client payload proves safe account-neutral replay.
- Fail fast with an actionable continuity error when replay cannot be proven safe, fencing poisoned anchors and avoiding retry-circuit cascades.
- Add regression coverage for owner rate-limit, successful cross-account replay and unsafe replay.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: allow safe cross-account continuation recovery and explicit unsafe-replay errors.
- `sticky-session-operations`: release temporary owner affinity only after account-neutral replay proof.

## Impact

Proxy HTTP/WebSocket bridge, load balancing, retry-circuit state, migrations and tests. Upstream beta.5 migrations must retain the existing fork migration head and account-assignment data.
