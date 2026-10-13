# Proposal

## Why

The running beta.9 instance returned a Codex capacity 429 followed by 70 owner-unavailable 502s while other accounts served requests. Temporary owner backoff is surfaced immediately, and stored successful turns are not used to recover a continuation whose client history fails the existing prefix proof.

## What Changes

- Recognize the observed Codex capacity message in the existing bounded capacity retry path.
- Wait up to 30 seconds for a temporarily backed-off active continuity owner, within the original request deadline and without holding account capacity.
- On definitive selection-time owner loss, reconstruct a portable continuation from the bounded, complete durable transcript and reuse the existing account-neutral bridge replacement path.
- Capture successful unanchored bridge roots after completion so later parent chains have a recorded beginning, without changing live retry decisions.
- Preserve scope, file ownership, single-account routing, tool settlement, response identity, and cancellation cleanup.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: bounded transient owner recovery and definitive durable conversation relocation.

## Impact

HTTP session bridge admission, upstream capacity classification, durable transcript loading and pure replay assembly; route and regression tests. No new setting, migration, or dependency. Ambiguous already-dispatched operations retain their existing behavior. The broader `relocate-anchored-turns-across-accounts` change remains separate.
