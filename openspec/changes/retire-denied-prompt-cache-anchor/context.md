# Denied prompt-cache anchor retirement

## Purpose and scope

This change closes one fork-specific lifecycle hole in the opt-in prompt-cache continuation path. The governing requirements remain in the `responses-api-compat` delta spec; this note records why sequencing matters and what is deliberately out of scope.

## Decision

The bridge captures and retires the exact denied proxy-injected anchor while the request still carries its original provenance. Only after that bookkeeping attempt does it install the preserved full-resend body and enter the existing bounded retry path. This ordering is required for both retry results: `true` proves only that a replay frame was sent, not that a replacement `response.completed` established a new anchor, while `false` must not leave the stale carrier reusable.

Retirement remains compare-and-clear. If a sibling completion has already advanced the session, the newer response stays current; only the denied id is fenced. Existing account and file ownership rules remain authoritative for replay routing.

## Constraints and non-goals

- Keep the per-key toggle default off and change no configuration surface.
- Do not retire client-supplied anchors or injected delta-only anchors.
- Do not broaden retry eligibility, account switching, or replay count.
- Do not add provider calls, production inference, live database access, migrations, or deployment work.
- Preserve downstream error behavior when retirement bookkeeping fails.

## Failure modes covered

- A retry boundary returning success without a later completion must not allow the denied id onto the next submit.
- A retry boundary returning failure must still leave the denied id fenced.
- A newer sibling completion, unrelated alias, other account, and file ownership must survive exact-id retirement.
- A request prepared while retirement is publishing must either send before publication owns the lifecycle boundary or fail closed at final dispatch.

## Example

Given stored anchor `resp-denied`, an opted-in exact-prefix full resend is trimmed and sent with that id. Upstream rejects it. The bridge first fences `resp-denied`, then retries the untouched full request without an anchor. If that replay is interrupted before completion, the next full resend is sent in full and never receives `resp-denied`; a concurrent `resp-newer` completion remains the session's current anchor.
