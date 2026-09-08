## ADDED Requirements

### Requirement: Integrated usage errors preserve recoverable fork accounts

Usage refresh MUST NOT deactivate an account solely because of HTTP 404 or 402. Explicit terminal error signals MUST retain their terminal semantics. Borrowed accounts MUST obtain credentials from their configured vending source rather than refreshing an owner token locally.

#### Scenario: Ambiguous usage status
- **WHEN** usage refresh returns HTTP 404 or 402 without an explicit terminal signal
- **THEN** the account remains recoverable without permanent deactivation

#### Scenario: Borrowed account recovery
- **WHEN** force probe successfully vends credentials for a borrowed account
- **THEN** the borrowed account recovers without requiring successful inference on the owner's upstream account
