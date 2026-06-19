# Tasks

## 1. Telemetry hook + metric
- [x] 1.1 Add `codex_lb_account_status_transition_total{status,error_code,source}` counter to `app/core/metrics/prometheus.py` (with `PROMETHEUS_AVAILABLE=False` fallback and `__all__`).
- [x] 1.2 Add `app/core/auth/reauth_telemetry.py` with `record_account_status_transition(account, *, status, error_code, source)` and the `REAUTH_SOURCE_*` constants; log includes `last_refresh` age and never token material.

## 2. Wire flip-sites
- [x] 2.1 `AuthManager.refresh_account` permanent-failure branch → `source=token_refresh` (only on a real flip, not the refresh-token-changed race-recovery early return).
- [x] 2.2 `UsageUpdater._deactivate_for_client_error` → `source=usage_refresh`, `error_code = exc.code or http_<status>`.
- [x] 2.3 `LoadBalancer.mark_permanent_failure` → `source=proxy`, `status = state.status`.

## 3. Tests
- [ ] 3.1 Hook: counter increments with correct labels; warning logged; `last_refresh` age formatted; missing/`None` last_refresh degrades to `unknown`; `PROMETHEUS_AVAILABLE=False` is a no-op for the counter.
- [ ] 3.2 Each flip-site invokes the hook with the expected `error_code` and `source`; the race-recovery early return in `refresh_account` does NOT record a transition.

## 4. Validate
- [ ] 4.1 `uv run ruff check` + `uv run ruff format --check` on touched files.
- [ ] 4.2 `uv run pytest` for the new + adjacent suites (auth manager, usage updater, load balancer refresh, metrics).
- [ ] 4.3 `openspec validate --specs`.
