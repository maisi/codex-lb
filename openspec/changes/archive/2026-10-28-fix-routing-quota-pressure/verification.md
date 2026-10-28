# Verification

Verified locally on 2026-10-28 before the subsequently requested commit and
push. No production container or configuration was modified.

## Completeness

All four implementation tasks are complete. Delta blocks for account-routing,
proxy-runtime-observability, and frontend-architecture match their synced main
spec blocks exactly. Stable rationale and rollout notes are in account-routing
context; the existing routing guide links to its owning spec and context.

## Correctness

- Eight initial focused regressions failed against the old state builder,
  including the reported jump from 8%/15% to 100%/100%, then passed with the fix.
- 407 routing, trace, sticky-selection, and routing-tunable unit tests pass.
- Eight routing API integration tests pass. Six parameterizations hold a real
  concurrent proxy operation open on `/v1/responses`, the Codex Responses alias,
  and `/v1/responses/compact`, with ordinary and absent primary windows. They
  assert the burn-first tier, stable quota before/during/after, live token
  reservation, successful held-request completion, and complete lease release.
- 242 concurrency, HTTP-bridge idle-lease, error-rate weighting, API-key priority,
  routed-stream release, and multi-replica regression tests pass.
- 50 frontend tests pass across routing settings and request routing details;
  the 45 settings tests were rerun after the final localized help-copy changes.
- Two Playwright screenshot scenarios pass and render synthetic before/after
  routing snapshots with 100%/100% versus observed 8%/15% quota. Captures are
  stored under docs/screenshots/routing-quota-pressure-{before,after}.jpg;
  their generator passes ESLint. The PR embeds both images for visual review.
- Weighted-draw tests cover both capacity-weighted and relative-availability
  selection, composition with existing error-rate weights, zero load weights,
  and the documented per-million-token normalization. Existing quota-threshold
  tier fallback tests continue to pass.

## Coherence and checks

The state builder retains normalized quota and composes local load into the
existing selection multiplier, without new model/API fields or settings.
Lease acquisition, ownership, release, cap admission, and latency weighting
are unchanged. The patch changes three runtime Python files; other changes
are tests, existing help copy, and governed documentation.

Ruff check and format checks, scoped ty checks, proxy architecture,
cancellation safety, proxy timing seams, settings-tier checks, and
`git diff --check` all pass. `openspec validate fix-routing-quota-pressure
--strict` passes. `openspec validate --specs` reports 68 passed and zero failed;
it retains existing warnings about long requirement descriptions elsewhere.

No completeness, correctness, or coherence blocker remains. The application
must be deployed before production requests use the corrected behavior.

Before the requested push, the full manual local-CI hook was attempted with
`uv run --frozen pre-commit run local-ci --hook-stage manual --all-files`.
It could not start `make ci` because `make` is not installed in this Windows
environment. The scoped checks above passed; full CI parity is not claimed.
