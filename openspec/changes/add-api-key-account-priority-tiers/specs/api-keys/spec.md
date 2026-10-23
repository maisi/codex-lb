# API keys — ranked account tiers

## ADDED Requirements

### Requirement: API keys accept account assignments as rank tiers

API key create and update requests SHALL accept `assigned_account_tiers`, a list
of account id lists ordered most-preferred first, as an alternative to
`assigned_account_ids`. Accounts in the same inner list SHALL share one
selection rank. A flat `assigned_account_ids` list SHALL keep assigning every
account its own rank in list order. A request that supplies both fields SHALL be
rejected with `invalid_api_key_payload`. Blank ids, repeated ids after their
first occurrence, and tiers left empty SHALL be dropped. API key responses SHALL
include `assigned_account_tiers` alongside `assigned_account_ids`, which SHALL
remain the flattened tier order.

#### Scenario: Tiers round-trip through the API

- **WHEN** a key is created with `assigned_account_tiers` `[["a", "b"], ["c"]]`
- **THEN** the response lists `assigned_account_tiers` with `a` and `b` in the
  first tier and `c` in the second
- **AND** `assigned_account_ids` lists the same accounts in tier order

#### Scenario: A flat list keeps one account per rank

- **WHEN** a key is updated with `assigned_account_ids` `["b", "c", "a"]`
- **THEN** the response lists `assigned_account_tiers` `[["b"], ["c"], ["a"]]`

#### Scenario: Both assignment forms at once are rejected

- **WHEN** a create or update request supplies `assigned_account_ids` and
  `assigned_account_tiers`
- **THEN** the request fails with `invalid_api_key_payload`

#### Scenario: Keys assigned before ranking keep their order

- **GIVEN** a key whose stored assignments all share the legacy priority 0
- **WHEN** the database is migrated
- **THEN** the key's assignments receive distinct ranks in their previous
  selection order
