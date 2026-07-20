## ADDED Requirements

### Requirement: Accounts expose a distinct immediate warmup action
The Accounts page SHALL provide a `Warm now` action that is visibly and behaviorally distinct from `Force probe`. Invoking `Warm now` MUST immediately request compact warmup for the selected account without opening a confirmation dialog.

#### Scenario: Operator warms an active account
- **WHEN** a dashboard operator with write access invokes `Warm now` for an active account
- **THEN** the frontend requests targeted warmup using that account's identifier
- **AND** prevents a duplicate invocation while the request is pending

#### Scenario: Warmup action is unavailable
- **WHEN** an account is not active or the current dashboard session is read-only
- **THEN** the frontend disables or omits the `Warm now` action according to the existing account-action convention
- **AND** does not issue a warmup request

#### Scenario: Structured warmup succeeds
- **WHEN** targeted warmup returns a successful structured result
- **THEN** the frontend displays localized success feedback for the selected account
- **AND** refreshes affected account and request-log data

#### Scenario: Structured warmup fails
- **WHEN** targeted warmup returns a structured unsuccessful result or an HTTP error
- **THEN** the frontend displays localized failure feedback using the available result message
- **AND** restores the action to an invokable state

#### Scenario: Force probe remains separate
- **WHEN** the operator views actions for an eligible account
- **THEN** `Warm now` and `Force probe` remain separately labeled actions
- **AND** each action calls only its own endpoint
