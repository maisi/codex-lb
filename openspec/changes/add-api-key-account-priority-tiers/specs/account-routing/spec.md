# Account routing — shared per-key ranks

## ADDED Requirements

### Requirement: Accounts sharing a per-key rank are balanced by policy and strategy

When an API key places several accounts in one rank tier, fresh account
selection for that key SHALL treat the eligible accounts of the serving tier as
one pool, ordered by account `routing_policy` and the configured routing
strategy, and SHALL NOT select an account from a lower tier while an account of
the serving tier can serve.

#### Scenario: Routing policy decides inside a shared rank

- **GIVEN** a key with tiers `[[A, B], [C]]`
- **AND** account B has routing policy `burn_first`, A has `normal`, and C has
  `burn_first`
- **AND** all three accounts are eligible
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account B is selected

#### Scenario: Strategy balances inside a shared rank

- **GIVEN** a key with tiers `[[A, B], [C]]` and all accounts `normal`
- **AND** account A has used far more of its quota than account B
- **AND** the routing strategy is `usage_weighted`
- **WHEN** a request with that key needs a fresh account selection
- **THEN** account B is selected
- **AND** account C is not selected while A or B can serve
