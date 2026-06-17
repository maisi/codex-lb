## Why

Background usage refresh can receive HTTP 404 from `/backend-api/wham/usage` for accounts that are still usable for normal proxy traffic. codex-lb currently treats usage 404 as an account-deactivation signal, which can remove a working account from routing and leave the operator with only re-authentication as the visible recovery path.

## What Changes

- Treat usage-refresh HTTP 404 as a non-deactivating refresh failure unless the upstream message explicitly says the OpenAI account is deactivated.
- Allow operators to force-probe accounts deactivated only by the usage 404 path.
- Reactivate a usage-404-deactivated account when the force probe receives a successful upstream status.
- Keep `reauth_required` accounts and other deactivated accounts on the re-authentication path.

## Capabilities

### Modified Capabilities

- `usage-refresh-policy`: usage 404 no longer deactivates by status alone; probe can recover usage-404 false positives.
- `frontend-architecture`: the Accounts page enables Force probe for usage-404-deactivated accounts only.

## Impact

- Code: `app/modules/usage/updater.py`, `app/modules/accounts/service.py`, `frontend/src/features/accounts/*`
- Tests: usage refresh, account probe service, account action UI
- Operator effect: false-positive usage 404 deactivations can be checked and recovered without OAuth re-authentication.
