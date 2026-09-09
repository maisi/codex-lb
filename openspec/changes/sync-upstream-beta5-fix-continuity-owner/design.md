## Context

The client can resend a complete Responses history without a hard account-scoped anchor. A rate-limited owner cannot serve the next turn, but the complete payload may be replayable on another compatible account. Existing durable bridge ownership must remain hard when the payload contains account-scoped files, unresolved tool state, previous response identifiers or non-neutral metadata.

## Goals / Non-Goals

**Goals:** recover only verified account-neutral full resends; preserve request ownership and settlement invariants; adopt all upstream beta.5 lifecycle code.

**Non-Goals:** moving arbitrary sessions between accounts, bypassing explicit client continuity anchors, or changing standard account selection.

## Decisions

Merge upstream first and resolve conflicts with upstream lifecycle code as the baseline. At owner-unavailable selection, classify the request using the canonical Responses payload projection already used for stale-anchor recovery. Require no nonblank previous response, conversation or account-scoped input references, and require complete prior output/tool context. Atomically retire the unavailable soft anchor, exclude its owner for this retry, select another eligible account, and dispatch a fresh full replay. If any proof is missing, return a dedicated actionable continuity error without opening another retry attempt.

Preserve the fork's hard owner forwarding path for explicit turn state and client-provided previous response IDs. Reuse existing quarantine generations and durable compare-and-set rather than adding a second anchor registry.

## Risks / Trade-offs

- [Risk] concurrent recovery races; [Mitigation] owner/epoch compare-and-set and quarantine-generation fences.
- [Risk] account-scoped payload replay leaks context; [Mitigation] fail closed on any ambiguity and retain hard ownership.
- [Risk] upstream migration heads diverge; [Mitigation] inspect Alembic graph and add one merge revision if required.
