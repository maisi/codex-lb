## ADDED Requirements

### Requirement: Safe recovery from temporary continuity-owner unavailability

When a Responses request is pinned to a temporarily unavailable continuity owner, the proxy MUST recover onto another compatible eligible account only after proving that the complete client payload is account-neutral and self-contained. The recovery MUST retire the soft owner atomically, exclude that owner for the recovery attempt, send a fresh full replay, and preserve the client session. If proof is unavailable, the proxy MUST fail quickly with an actionable continuity error and MUST NOT retry a poisoned anchor.

#### Scenario: Rate-limited owner has a safe full replay
- **WHEN** the owner is rate-limited, another compatible account is eligible, and the client payload has no account-scoped references or unresolved state
- **THEN** the proxy retires the soft owner, selects the eligible account, sends a fresh full replay, and returns the continued response

#### Scenario: Replay is account-scoped or ambiguous
- **WHEN** the owner is unavailable and the payload contains a nonblank previous response, conversation, account-scoped file/image, unresolved tool state, or incomplete history
- **THEN** the proxy fails quickly with an actionable continuity error and does not switch accounts

### Requirement: No poisoned-anchor retry cascade

A failed continuity-owner recovery MUST fence the associated stale anchor and MUST NOT repeatedly reopen the retry circuit for the same client turn.

#### Scenario: Recovery fails after anchor rejection
- **WHEN** an upstream stale-anchor rejection occurs during owner recovery
- **THEN** the anchor is quarantined once, the client receives one terminal continuity error, and subsequent retries do not enter a 60-second poisoned-anchor cooldown
