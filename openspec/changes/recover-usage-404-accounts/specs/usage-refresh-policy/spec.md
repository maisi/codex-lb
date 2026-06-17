## MODIFIED Requirements

### Requirement: Usage refresh cools down repeated auth-like failures

Background usage refresh MUST apply a cooldown to accounts that repeatedly fail usage refresh with ambiguous `401`, `403`, or `404` responses. Accounts in that cooldown window MUST be skipped until the cooldown expires or a later successful refresh clears it.

#### Scenario: Ambiguous usage 404 enters cooldown

- **WHEN** usage refresh receives HTTP `404`
- **AND** the upstream message does not explicitly indicate the OpenAI account has been deactivated
- **THEN** the account is not deactivated immediately
- **AND** subsequent refresh cycles skip the account until the cooldown window expires

### Requirement: Usage refresh deactivates on clear deactivation signals

The system MUST deactivate accounts when usage refresh receives a permanent deactivation signal. At minimum, `402` responses, permanent authentication error codes, and responses whose message explicitly indicates that the OpenAI account has been deactivated MUST be treated as deactivation signals. HTTP `404` alone MUST NOT be treated as a deactivation signal.

#### Scenario: Usage 404 without deactivation message does not deactivate the account

- **WHEN** usage refresh receives HTTP `404`
- **AND** the upstream message does not state that the OpenAI account has been deactivated
- **THEN** the account status remains unchanged

### Requirement: Usage-404-deactivated accounts can be recovered by force probe

Accounts deactivated by the legacy usage-refresh HTTP `404` classification MUST be eligible for an operator force probe. When that force probe receives a successful upstream status, codex-lb MUST reactivate the account and clear the deactivation reason. Accounts in `reauth_required` or deactivated for other reasons MUST remain ineligible for force probe recovery.

#### Scenario: Successful force probe recovers usage-404 deactivation

- **GIVEN** an account is `deactivated`
- **AND** its deactivation reason starts with `Usage API error: HTTP 404`
- **WHEN** an operator force-probes that account
- **AND** the upstream probe returns a successful status
- **THEN** codex-lb marks the account `active`
- **AND** clears the deactivation reason

#### Scenario: Failed force probe does not recover usage-404 deactivation

- **GIVEN** an account is `deactivated`
- **AND** its deactivation reason starts with `Usage API error: HTTP 404`
- **WHEN** an operator force-probes that account
- **AND** the upstream probe returns an unsuccessful status or network-failure sentinel
- **THEN** codex-lb leaves the account status unchanged
