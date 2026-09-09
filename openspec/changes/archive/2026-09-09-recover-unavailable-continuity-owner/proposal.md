## Why

Issue #27 describes existing Codex sessions stranded on a rate-limited owner while another compatible account can serve them. Upstream already projects proven full context into an account-neutral replay, but rejects a complete tool batch followed by fresh user input even when durable metadata proves the batch complete. Unsafe requests also receive only an instruction to retry later.

## What Changes

- Admit fresh user input after an exact, complete durable tool manifest, preserving strict whole-body account-neutral validation and existing owner fencing.
- Preserve calls, results and new input in the replay; remove the old account-bound anchor through the existing recovery path and continue on an eligible replacement.
- Make unreplayable owner-unavailable errors actionable while retaining stable error codes.
- Prove public HTTP recovery on a rate/usage-limited owner, continued replacement ownership, unsafe replay rejection and bounded repeated failures.

## Capabilities

### Modified Capabilities

- `responses-api-compat`: prove a complete tool batch with trailing fresh input and provide actionable unreplayable-owner errors.

## Impact

Replay proof, continuity error text and regression coverage. No settings, schema, dashboard or default changes. Refs #27 and upstream #1707/#2121. Opaque compaction or account-owned files remain nonportable.
