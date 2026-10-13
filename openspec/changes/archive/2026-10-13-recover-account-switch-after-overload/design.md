# Design

## Context

See proposal.md for the incident. The bridge already owns a bounded capacity wait, strict account-neutral projection, replacement-session routing and durable settled response spools. Reuse those paths rather than create another retry transport.

## Goals / Non-Goals

Recover the observed HTTP bridge chain while preserving account ownership, scope and settlement. Do not retry ambiguous dispatches or add durable capture to the downstream WebSocket transport.

## Decisions

- Extend the existing capacity message classifier with the native Codex wording. Keep capacity code precedence and existing replay bounds.
- Read fresh account status and local runtime backoff under the balancer's account lock. Sleep without a database session, stream lease or response-create admission. The owner wait has one 30-second budget per incoming request, bounded by the original deadline.
- Add a pure stored-transcript assembler. The repository returns oldest-first turns; verify parent linkage, scope, settled terminal response IDs and whole-transcript bounds (128 turns, 8 MiB, 8192 items). Missing material declines.
- Capture successful unanchored HTTP bridge roots and replacement turns only once their settled terminal response supplies complete output. Reuse the operation ledger/spool and give independent roots unique fingerprints. This optional capture leaves live dispatch/reconnect decisions unchanged; existing anchored duplicate suppression and ownership fencing remain in force. Historical chains with an unrecorded root are unavailable for reconstruction.
- Apply the existing projection to stored history and current input, then require the existing strict whole-payload predicate. Join only a matching accumulated tail to the current prefix, using linear-time prefix matching and positively enumerated recursive semantic keys. Current input is never discarded. Recording IDs and bookkeeping do not identify messages; text, roles, call IDs and tool arguments do.
- Load durable material only after a selection-time owner miss, with a short bounded I/O deadline. Reuse `switch_to_account_neutral_replay`, which removes stale affinity headers, creates a replacement key, excludes the failed owner and preserves normal account/security selection.
- Decline single-account routing, file-bound requests, absent scoped durable ownership, incomplete tool pairs and unknown request state. A pre-submit selector rejection is definitive; absence of output alone is not evidence for replay.

## Risks / Trade-offs

Rebuilding resends context and may lose cache reuse; it prevents a dead thread. Corrupt or incomplete spools keep the existing failure. A 30-second wait can add latency when the owner stays unavailable; it is bounded and cancellable. Relocation cannot recover an account-specific uploaded file or an unresolved tool call.

## Migration Plan

No schema or configuration change. Deploy the tested code through the existing release path. Rollback restores the previous retry behavior without changing stored data.
