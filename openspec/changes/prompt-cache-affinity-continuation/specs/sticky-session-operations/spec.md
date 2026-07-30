## ADDED Requirements

### Requirement: Prompt-cache affinity remains soft outside a proven turn

Enabling prompt-cache continuation for an API key MUST NOT make its prompt-cache affinity mapping globally hard. Only a turn with a proven previous-response owner MAY become owner-bound, and account or owner conflict MUST fail closed or use the documented full-resend path rather than crossing accounts.

#### Scenario: Unproven cache-affinity request can use legacy routing
- **WHEN** an opted-in request has no proven continuation anchor
- **THEN** the prompt-cache mapping retains existing soft-affinity routing behavior

#### Scenario: Proven continuation cannot cross accounts
- **WHEN** the stored response owner differs from the selected account
- **THEN** the service does not send that continuation through the different account
