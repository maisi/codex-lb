## Why

The fork needs all upstream fixes through 15ccd901 (v1.25.0-beta.4) while retaining its operator features and deployed data. Duplicate implementations increase maintenance and can discard upstream lifecycle fixes during conflict resolution.

## What Changes

- Integrate upstream history and its accompanying specs, tests, native transport, dashboard and lifecycle changes.
- Preserve token vending, borrowed-account lifecycle, account ranking, prompt-cache continuation, cache reports, request-log preferences, forced usage, targeted warmup and fork publishing policies.
- Consolidate usage-error classification on upstream explicit-terminal semantics, retaining recovery of historical false deactivations.
- Merge migration heads without rewriting deployed revisions.

## Capabilities

### New Capabilities

None beyond capabilities supplied by upstream's existing change artifacts.

### Modified Capabilities

- `usage-refresh-policy`: combine upstream nonterminal HTTP errors with fork recovery and borrowed-account lifecycle.
- `github-automation`: distinguish verified upstream release imports from fork-authored beta releases.
- `database-migrations`: upgrade both existing fork databases and upstream databases through the combined graph.

## Impact

Proxy, account lifecycle, database, dashboard, CI and native Rust packaging. Upstream requirements arrive with their owning artifacts; fork requirements remain in their existing changes. No fork setting or persisted field is intentionally removed.
