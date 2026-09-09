## ADDED Requirements

### Requirement: Complete tool context permits a fresh user follow-up during owner recovery

When a Responses continuation has a fingerprint-verified durable input prefix and every call and matching result in the recorded prior-response tool manifest, the replay proof MUST permit a trailing self-contained user-input suffix. The proof MUST validate the complete suffix against the canonical account-neutral allowed-fields and content contract and MUST preserve exact call IDs, call types, ordering, complete results and collision checks. It MUST reject user input interleaved with incomplete results and any subsequent call, result, assistant or developer item. The existing bounded developer-interleave exception MUST NOT gain a trailing-input extension.

Cross-account recovery MUST still require full context, account-neutral projection, existing account scope and file ownership checks, and safe pre-dispatch state. Recovery MUST preserve all proven calls, results and new input, remove the unavailable owner's upstream anchor through the existing fenced recovery path, and allow the client session to continue on the eligible replacement. Explicit previous-response references alone MUST NOT authorize replay.

#### Scenario: Complete batch resumes on another account
- **GIVEN** an existing session's owner becomes temporarily rate/usage limited and another compatible account is eligible
- **AND** a full resend matches the stored prefix and completes the exact recorded tool batch before appending fresh user input
- **WHEN** the complete projected request is account-neutral and safe to dispatch
- **THEN** the bridge replays it without the old anchor on the replacement
- **AND** a later anchored continuation stays on that replacement

#### Scenario: Fresh input cannot conceal missing or account-owned context
- **WHEN** the input omits a recorded tool result, introduces a duplicate or mismatched call, interleaves user input, or contains account-owned files, unknown ownership fields or opaque compaction state
- **THEN** the proof MUST reject cross-account replay

### Requirement: Unrecoverable owner failures give actionable continuity guidance

An unavailable-owner request whose safe replay cannot be proven MUST fail with its stable continuity error code and guidance to resend complete account-neutral history without the old response anchor or start a new session. A pre-dispatch proof rejection MUST NOT submit to another account or count as an upstream transport failure that opens a poisoned-anchor retry circuit.

#### Scenario: Repeating an unsafe full resend fails without poisoning the retry circuit
- **GIVEN** an unavailable owner and an unsafe or incomplete replay
- **WHEN** the client repeats the request
- **THEN** each request fails with actionable continuity guidance before upstream submission
- **AND** the rejection does not create an upstream-timeout cooldown
