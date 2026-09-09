## ADDED Requirements

### Requirement: Temporary owner recovery preserves hard continuity

Soft prompt-cache affinity MAY be released for account-neutral full replay, but raw turn-state and explicit client continuity ownership MUST remain hard and account-bound.

#### Scenario: Soft affinity is released
- **WHEN** safe replay proof succeeds for a temporary owner failure
- **THEN** the old soft mapping is retired atomically and the replacement mapping is established by normal selection

#### Scenario: Hard continuity is retained
- **WHEN** the request contains explicit turn-state or client-provided previous-response ownership
- **THEN** the proxy keeps the owner-bound route and returns an actionable owner-unavailable error if it cannot serve
