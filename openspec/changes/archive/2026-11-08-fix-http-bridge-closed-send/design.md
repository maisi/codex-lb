## Context

See proposal.md for the incident. The submit handler already converts ordinary transport exceptions to `ProxyResponseError(502)`. A route regression reproduces the escape: the API's native-client failure policy replays that handled startup error into a committed stream and deliberately raises it again, retaining the native send exception as its cause. Internal owner forwarding inherits the client's native user agent and encounters the same policy. Native closed-before-send rejection also uses the same metadata as a potentially dispatched command, losing the distinction required for safe recovery. Reconnect and resource close both mutate a shared session and need explicit lifecycle ownership.

## Goals / Non-Goals

**Goals:** retain positive dispatch evidence, bound retry to one same-account reconnect, reuse terminal settlement, and verify the local and owner routes with actual native adapters.

**Non-Goals:** speculative replay, account failover, transport-policy changes, new settings, and production service access.

## Decisions

- Add explicit pre-dispatch evidence only at the native local closed check; default all other errors to ambiguous. Do not infer safety from error strings, phase names, or the absence of `response.created`.
- Keep a proven pre-dispatch retry inside submit's lifecycle ownership and existing request admission. Preserve the exact request and anchor, require the same account, and let a second failure reach the established failure handler. Do not recursively re-submit or register a second durable operation.
- Classify settled submit failures with the existing error phase field. Native HTTP startup returns their ordinary 502, and an already-committed stream emits an unmarked terminal failure. A private owner-response header preserves this classification across forwarding without claiming ambiguous sends were pre-dispatch. Other native transport lifecycle policies remain governed by their existing requirements.
- Prevent reconnect from racing a resource-close owner. Connection replacement must not revive a session being retired, and cleanup for an old connection must finish before replacement becomes eligible for reuse.
- Add behavioral tests for closed native sockets, exhausted retry, ambiguous delivery, settlement, and signed internal forwarding. Keep regression assertions on dispatch count, error envelopes and released ownership.

## Risks / Trade-offs

- Incorrect pre-dispatch evidence could duplicate a turn → set it only before any command is emitted, and cover an error after command dispatch as ambiguous.
- Retrying an anchored or file-bound request on a different account could lose context → require the same account and retain existing pin validation.
- Reader/close overlap could settle the request twice → hold lifecycle ownership while swapping sockets and retain the established finalization owner.

## Migration Plan

No migration or configuration changes. Ordinary deployment and rollback suffice; production verification remains outside this worktree task.
