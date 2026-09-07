# Upstream integration evidence

Integrated upstream 15ccd901 (v1.25.0-beta.4) into fork 5e90f875. The merge preserves upstream ancestry for subsequent synchronizations.

## Preserved behavior

Token vending and borrowed-account recovery/background isolation; API-key account ranks and scope; prompt-cache continuation and bounded observability; forced streaming usage; cache reports; configurable request-log columns; targeted warmup and reset detection; reauth transition telemetry; fork rolling Docker publishing.

Upstream non-native fingerprint normalization replaces the equivalent fork implementation. Upstream typed error-parameter handling replaces the fork field-presence workaround. Upstream cancellation, replay, overload backoff, native transport and usage-error classification are retained.

## Verification completed

- Frontend build, TypeScript and all 1,267 tests.
- Five browser smoke tests against an isolated real backend.
- Rust workspace tests.
- 107 Helm tests.
- 110 SQLite migration/account/report integration tests.
- Both migration-parent upgrade regressions preserve API-key flags and assignment ranks.
- Initial proxy integration run: 541 passed; four failures corrected and rerun successfully.
- Targeted backend regression rerun: 23 passed.
- Fork fingerprint, vending, priority and usage regression suite: 192 passed.
- Strict OpenSpec validation: all 58 capabilities; placeholder purpose text repaired without changing requirements.
- Python lint/type and proxy architecture, cancellation and timing checks.
- Wheel build and bundled frontend asset verification.

Full backend, PostgreSQL and native release-build checks are still running; this change remains active until verification completes.

## Dashboard evidence

[Before](screenshots/before.png) and [after](screenshots/after.png) use each revision's built frontend with synthetic account and request fixtures. Browser smoke separately checks real backend responses. Screenshots contain no production account data.

## Rollout

Back up the database, upgrade to the combined migration head, deploy through beta and monitor account recovery, reservation settlement and continuation failures. Stable promotion follows the repository soak policy. No deployment has been performed as part of local verification.
