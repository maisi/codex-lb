## Context

The existing HTTP bridge validates a durable prefix fingerprint and retains either a prior assistant response or the exact recorded pending-tool manifest. Its account-neutral projection drops owner-bound reasoning only when enough plaintext context remains. The manifest checker currently requires every suffix item to be a tool call/result, so a following user instruction incorrectly invalidates complete context.

## Decisions

Split a suffix at its first fresh user input. Require every following item to be fresh input and validate it with the canonical self-contained replay classifier, including allowed fields and ownership metadata. Validate the earlier tool batch exactly against the durable manifest, preserving ordering, type, duplicate, collision and missing-result checks. Keep the existing bounded developer-interleave exception unchanged; it cannot be extended with a trailing suffix.

Reuse existing prefix proof, complete-body projection, account scope, file affinity, pre-dispatch gates, replacement session identity and durable ownership fencing. No new replay registry or broad abandonment of explicit continuity. Explicit previous-response references may be removed only where existing full-context proof authorizes it.

Keep the existing owner-unavailable error code but explain that a complete account-neutral resend without the old anchor, or a new session, is required when recovery cannot be proven. Verify HTTP and direct-WebSocket error contracts and that pre-dispatch rejection does not consume the retry circuit.

## Constraints and failure modes

Fresh input must not hide a missing parallel result or introduce unknown account-owned metadata. Opaque encrypted compaction, conversation references, file ownership, incomplete/mismatched prefixes and in-flight ambiguous outcomes remain fail-closed. A quota-limited owner A with a complete proven tool result plus a new goal instruction can recover to eligible B; a file owned by A cannot.
