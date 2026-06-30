## Why

Operators report that accounts "regularly need re-auth", but the runtime is blind to *why*: when an account is flipped to `REAUTH_REQUIRED` or `DEACTIVATED`, the `app.modules.accounts.auth_manager` path emits nothing, there is no Prometheus signal, and the upstream error code (e.g. `invalid_grant`, `refresh_token_reused`, `token_expired`, `token_invalidated`) plus how stale the credentials were is dropped at the repository layer. This makes it impossible to distinguish the competing causes — idle credential aging, upstream session/ban-wave revocation, or cross-instance refresh-token rotation collisions — from logs and metrics.

## What Changes

- Add a single observability hook, `record_account_status_transition`, that emits a `WARNING` log and a Prometheus counter whenever an account is flipped to a non-routable auth status.
- Add the `codex_lb_account_status_transition_total{status,error_code,source}` counter (low-cardinality: `status` ∈ {`reauth_required`,`deactivated`}, `source` ∈ {`token_refresh`,`usage_refresh`,`proxy`}, `error_code` is the bounded upstream code).
- Record the account's `last_refresh` age (seconds) at flip time in the log so idle-aging is directly observable.
- Wire the hook into the three flip-sites where the error code is in scope: the token-refresh path (`AuthManager.refresh_account`), the usage-refresh path (`UsageUpdater._deactivate_for_client_error`), and the proxy data path (`LoadBalancer.mark_permanent_failure`).
- Never log token material.

## Impact

- Affects auth-status observability only; no routing, persistence, or auth decision behavior changes.
- Adds `app/core/auth/reauth_telemetry.py` and one Prometheus counter.
- Adds unit coverage for the hook (counter + log + credential-age formatting) and for each of the three flip-sites invoking it with the correct `error_code`/`source`.
- Spec: `proxy-runtime-observability`.
