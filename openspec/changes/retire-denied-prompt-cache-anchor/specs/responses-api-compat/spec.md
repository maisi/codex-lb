## ADDED Requirements

### Requirement: Prompt-cache fallback retires its exact denied anchor before replay

When upstream rejects a proxy-injected prompt-cache continuation anchor with `previous_response_not_found`, the HTTP bridge MUST publish the denial fence and attempt exact-id retirement while the failed request still carries its anchor provenance. Retirement MUST precede replacement of the anchored request body with the preserved full-resend body and MUST precede every early return from the fresh-replay path. The fresh replay MUST contain the complete preserved input and MUST NOT contain `previous_response_id`.

The retirement MUST affect only the denied anchor. A newer sibling completion, an unrelated response alias, another account's continuity state, and account-scoped file ownership MUST remain unchanged. An already-prepared request carrying the denied proxy-injected anchor MUST remain subject to the final dispatch fence. Keys for which prompt-cache continuation is disabled MUST retain their unanchored full-resend behavior.

#### Scenario: Successful replay send does not certify a replacement anchor

- **GIVEN** an opted-in exact-prefix prompt-cache continuation carries a proxy-injected anchor and retains a proven full-resend body
- **WHEN** upstream denies the anchor and the fresh-replay send reports success without a later completion
- **THEN** the denied anchor is fenced before the fresh body is installed
- **AND** the replay sends the complete preserved input without `previous_response_id`
- **AND** the next eligible submit MUST NOT inject or trim against the denied anchor

#### Scenario: Failed replay send still retires the denied anchor

- **GIVEN** an opted-in exact-prefix prompt-cache continuation carries a proxy-injected anchor and retains a proven full-resend body
- **WHEN** upstream denies the anchor and the fresh-replay send reports failure
- **THEN** the denied anchor remains fenced
- **AND** the next eligible submit MUST NOT inject or trim against the denied anchor

#### Scenario: Exact retirement preserves newer and unrelated ownership state

- **GIVEN** a prompt-cache anchor is denied after a sibling completion has advanced the same session to a newer response
- **AND** unrelated response aliases, another account's continuity state, or account-scoped file ownership exist
- **WHEN** the denial is retired
- **THEN** the newer sibling response remains current
- **AND** only the denied response id is fenced or removed
- **AND** unrelated aliases, other-account continuity, and file ownership remain unchanged

#### Scenario: Concurrent prepared dispatch observes prompt-cache denial publication

- **GIVEN** one request has prepared a proxy-injected prompt-cache anchor for dispatch
- **AND** another request receives `previous_response_not_found` for that exact anchor
- **WHEN** denial publication wins lifecycle ownership before the prepared request's final send section
- **THEN** the prepared request fails closed without sending the denied anchor

#### Scenario: Disabled prompt-cache continuation remains unanchored

- **GIVEN** prompt-cache continuation is disabled for an API key
- **WHEN** the client submits the same full-resend sequence used by the denial regression
- **THEN** the bridge sends the full request without a proxy-injected `previous_response_id`
