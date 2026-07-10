## Context

codex-lb currently rewrites a non-native request's `User-Agent` to a Codex CLI value, but strips its `originator` and does not provide a `version` header. Controlled upstream tests show that `gpt-5.6-luna` succeeds only when both headers identify a current Codex CLI client; the model otherwise resolves to an unavailable rollout engine despite appearing in the authenticated model list.

Both HTTP Responses and Responses websocket paths call separate header builders. They already share the non-native fingerprint normalizer and the synchronous Codex-version cache.

## Goals / Non-Goals

**Goals:**
- Send one complete, consistent Codex CLI identity for non-native upstream Responses requests on both transports.
- Ensure client-supplied identity headers cannot select a third-party or stale rollout cohort.
- Reuse the cached Codex client version without adding network I/O to request handling.

**Non-Goals:**
- Change model aliases, model-catalog eligibility, account selection, or Responses Lite behavior.
- Alter the fingerprint of requests already identified as native Codex traffic.
- Guarantee entitlement to Luna for accounts whose upstream model catalog does not advertise it.

## Decisions

### Normalize `originator` and `version` with the existing User-Agent

The non-native normalizer will replace any inbound `originator` and `version` values with `originator: codex_cli_rs` and the same cached Codex version used to build the User-Agent. This matches the tested upstream routing identity and keeps the three related fields internally consistent.

The alternative of retaining the inbound originator or version would continue to permit the failing rollout cohort. Adding only a Responses Lite header is excluded because controlled upstream tests showed it does not change this routing result.

### Reuse the shared normalizer for HTTP and websocket headers

The existing shared normalizer is invoked by both upstream header builders. Extending it preserves parity without duplicating fingerprint rules or creating transport-specific behavior.

The alternative of patching only the HTTP builder would leave websocket-routed and continuity-token follow-up requests susceptible to the same failure.

### Preserve native Codex identities

Native Codex requests remain exempt from normalization so codex-lb keeps forwarding their original identity headers and account-header casing. This avoids claiming a different client version or originator on behalf of a first-party caller.

## Risks / Trade-offs

- [Upstream identity rules can change] → Use the existing live version cache and isolate all replacement behavior in the shared normalizer.
- [A third-party client intentionally sends `version`] → Replace it only for non-native upstream requests, where Codex CLI normalization is already the established behavior.
- [Luna remains unavailable for an account] → Preserve catalog eligibility and surface the upstream error; this change corrects routing identity rather than bypassing availability controls.

## Migration Plan

No data migration or configuration change is required. Deploy the code and monitor Luna request failures by model and upstream error. Roll back by reverting the header-normalization change; requests return to the prior non-native fingerprint.

## Open Questions

None.
