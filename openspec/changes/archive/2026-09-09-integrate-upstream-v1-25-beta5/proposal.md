## Why

Upstream has advanced 58 commits beyond the previously integrated beta.4. The fork needs beta.5 and subsequent routing, native transport and dashboard improvements while preserving its account vending, ranking, prompt-cache continuation, warmup and publishing behavior.

## What Changes

- Integrate upstream through `5794d8d7a70e113afae4df0d83b03058831f0bbd` with ancestry preserved.
- Reconcile promoted dashboard settings and extracted account-state helpers with fork features.
- Join deployed fork and upstream migration histories with a new merge revision.
- Preserve fork release provenance validation in upstream's separate release-guard workflow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-migrations`: converge beta.5 and deployed fork histories without losing fork data.

## Impact

Backend, native worker, dashboard, CI and OpenSpec contracts imported from upstream. Existing opt-in vending settings remain deployment topology/credentials. Issue #27 is handled as a separate follow-up change.
