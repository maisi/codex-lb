## Why

Upstream advanced another 20 commits after the beta5 integration snapshot, through `c0beaaadd96a89f0240582b5449bf4dd50647c7d`. The user requested the new upstream changes while preserving fork-only features.

## What Changes

- Merge beta6 and later routing, native HTTP streaming, permanent report aggregation, dashboard routing settings and configuration cleanup.
- Preserve fork token vending, per-key ranking, prompt-cache continuation, reports, warmup and release policy.
- Join new upstream migration history with the deployed fork branch without rewriting revision identities.

## Capabilities

### Modified Capabilities

- `database-migrations`: preserve fork policy while adding upstream report aggregates and routing settings.
- `report-aggregation`: retain historical API-key filters without full report computation.

## Impact

Backend, dashboard, native transport, reports, tests and OpenSpec. Issue #27 remains in its focused follow-up PR.
