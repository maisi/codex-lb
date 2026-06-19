# Context

## Purpose

Make the cause of account re-auth provable from telemetry. The operator symptom is "accounts regularly need re-auth, regardless of browser vs device login". Because both login flows converge on the same stored-refresh-token rotation path, the cause lives in the shared refresh/rotation/storage path — but the runtime currently emits no signal at the moment an account is flipped, so the competing hypotheses cannot be separated.

## Failure modes this disambiguates

- **Idle credential aging** — accounts not selected by traffic for longer than the refresh interval age out and flip with `token_expired` / `refresh_token_expired` and a large `last_refresh` age. (The Auth Guardian, `auth_guardian_enabled`, exists to prevent this and is disabled by default.)
- **Upstream session/ban-wave revocation** — bursts of `token_invalidated` / `refresh_token_invalidated`, server-side, not preventable in codex-lb.
- **Cross-instance refresh-token rotation collisions** — the same account loaded into two non-coordinating instances; each rotation invalidates the other holder's refresh token, surfacing as `invalid_grant` / `refresh_token_reused`. The in-process `_RefreshSingleflight` cannot coordinate across instances.

## Confirmation queries (after deploy)

- Loki: which `error_code` dominates the `Account auth status transition` log lines, and what is the `last_refresh_age_seconds` distribution at flip.
- Prometheus: `sum by (error_code, source) (increase(codex_lb_account_status_transition_total[7d]))`.
  - `token_expired`/`refresh_token_expired` with high age → idle-aging (enable Auth Guardian).
  - `token_invalidated`/`refresh_token_invalidated` bursts → upstream.
  - steady `invalid_grant`/`refresh_token_reused` → cross-instance rotation collision.

## Scope notes

- The `proxy` source is intentionally coarse: `LoadBalancer.mark_permanent_failure` is the chokepoint for ~25 proxy call sites (streaming, websocket, http-bridge, warmup, …) and does not know the precise caller. Finer attribution can be threaded later if needed.
- `error_code` is server-controlled and bounded in practice (the permanent-failure code set plus `http_<status>` fallbacks), keeping counter cardinality low.
