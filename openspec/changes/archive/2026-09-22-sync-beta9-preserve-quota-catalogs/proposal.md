## Why

The fork runs upstream beta6 and misses beta7–beta9 continuity recovery improvements. An observed outage also showed temporarily quota-exhausted owners disappearing from the authoritative model catalog, turning capacity exhaustion into a misleading policy conflict even with all accounts enabled.

## What Changes

- Integrate upstream `v1.25.0-beta.9` while retaining fork routing, token vending, pricing, reports, and main-only image publishing.
- Preserve last-known model capability evidence for temporarily rate-limited or quota-exhausted accounts without making them eligible to serve exhausted requests.
- Preserve genuine catalog removal, account removal, plan changes, and explicit policy restrictions.
- Reconcile upstream and fork migration histories with additive merge revisions and verify existing-data upgrades.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-catalog-compat`: Separate temporary account capacity from last-known model capability evidence.
- `database-migrations`: Upgrade the deployed fork and imported beta9 histories to one compatible head.

## Impact

Upstream release integration affects backend, dashboard, native egress, migrations, and validation tooling. The targeted fix affects model refresh/registry state and continuity selection; no new setting or API field is required. Deployment must use the combined integration and fix after migration and CI verification.
