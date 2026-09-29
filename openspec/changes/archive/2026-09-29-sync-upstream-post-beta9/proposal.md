## Why

Upstream `main` moved 42 commits past `v1.25.0-beta.9` (SCIM provisioning, subscription-overflow schema withdrawal, proxy/quota/shutdown fixes, dependency bumps). The fork should track them without losing fork routing, token vending, pricing, reports, or its deployed migration history.

## What Changes

- Merge `upstream/main` (`f8ffbac2`) into the fork and reconcile conflicts while preserving fork behavior.
- Add the operation-free merge revision `20260929_000000_merge_upstream_post_beta9_and_fork` joining the fork's beta9 merge head and upstream's `20260918_000000_merge_scim_and_overflow_heads`.
- Adapt migration tests to the retained fork head and the new single head.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-migrations`: Upgrade the deployed fork beta9 and upstream post-beta9 histories to one compatible head.

## Impact

Backend, dashboard, CI, and migrations follow upstream. No new setting or API field is introduced by the fork side of this sync.
