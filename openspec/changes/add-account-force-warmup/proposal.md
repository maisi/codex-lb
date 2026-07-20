## Why

Operators can force-probe an account for recovery, but cannot run the compact proxy warmup path for one selected account from the dashboard. The existing `/v1/warmup/force` endpoint warms an API key's whole account pool, making it unsuitable for a precise account action.

## What Changes

- Add a dashboard-authenticated endpoint that force-warms exactly one selected active account through the existing compact proxy warmup path.
- Preserve warmup routing, token vending, health handling, request logging, and accounting exclusions while bypassing usage eligibility for this explicit operator action.
- Add an immediate `Warm now` action to active accounts with read-only, busy, success, and structured-failure handling.
- Keep the existing recovery-oriented `Force probe` action unchanged and distinct.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `proxy-warmup`: Add targeted dashboard force-warmup semantics and a structured one-account result.
- `frontend-architecture`: Add the active-account `Warm now` action and operator feedback contract.

## Impact

- Backend: accounts dashboard API and proxy warmup service targeting.
- Frontend: account API client, mutation hook, actions, schemas, translations, and mocks.
- Tests: route-level backend regressions and Accounts page product-path coverage.
- Security: existing dashboard write authorization remains mandatory; borrowed accounts may use live token vending.
