## ADDED Requirements

### Requirement: Opted-in prompt-cache full resends may continue only with exact proof

For an API key whose prompt-cache continuation policy is true, the service MAY inject the latest stored `previous_response_id` only when API-key scope, model and account continuity, serialized ownership with no pending ambiguity, and an exact canonical match of the entire stored input prefix are proven. The service MUST forward only input items after the proven prefix and MUST retain the full incoming input metadata as the next continuity context.

#### Scenario: Exact full prefix continues
- **WHEN** an opted-in prompt-cache request extends the completed stored input with an exact full prefix on the same API key, model, and account owner
- **THEN** the service injects the completed response ID and forwards only the new suffix items

#### Scenario: Default-off key resends in full
- **WHEN** the API key policy is false or absent
- **THEN** the service does not implicitly inject a previous response for prompt-cache affinity

### Requirement: Ambiguous prompt-cache requests remain self-contained

The service MUST full-resend without an implicit anchor on prefix mismatch, shorter or unrelated input, compaction or rewrite, missing continuity metadata, concurrent/pending ambiguity, model mismatch, account or owner mismatch, or any other ambiguity. A weak affinity-key match alone MUST NOT establish continuation.

#### Scenario: Rewritten history skips continuation
- **WHEN** any item in the stored prefix differs from the incoming input
- **THEN** the request is forwarded as the original full resend without an injected anchor

#### Scenario: Concurrent turn is ambiguous
- **WHEN** another turn makes the candidate parent ambiguous before serialized send ownership
- **THEN** the request does not reuse the stale parent

### Requirement: Proxy-injected stale anchors fall back safely

If upstream rejects a proxy-injected prompt-cache continuation because the response is missing or expired, the service MUST retry once with the preserved original full-resend payload. Explicit client-supplied anchors MUST retain existing behavior.

#### Scenario: Injected response expired
- **WHEN** upstream rejects an implicitly injected response as missing or expired
- **THEN** the service retries the untouched full resend without `previous_response_id`

### Requirement: Request stage follows proven continuation

The service MUST classify a prompt-cache request as `follow_up` only after continuation proof and anchor injection. Skipped or fallback full resends MUST remain `first_turn`.

#### Scenario: Prefix mismatch stays first turn
- **WHEN** prompt-cache continuation proof fails before send
- **THEN** request stage remains `first_turn`
