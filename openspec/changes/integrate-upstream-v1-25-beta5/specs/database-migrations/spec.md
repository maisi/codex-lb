## ADDED Requirements

### Requirement: Beta5 integration preserves both deployed migration histories

The integrated schema MUST have a single head joining `20260908_000000_merge_upstream_beta4_and_fork` and `20260909_040000_dashboard_timeout_settings`. The merge revision MUST perform no schema or data operations and MUST preserve deployed revision identities. Upgrades MUST preserve credentials, API-key assignments, ranking, forced-usage and continuation policy while applying missing upstream and fork schema additions.

#### Scenario: Upgrade an existing beta4 fork database
- **GIVEN** a database at the beta4 fork merge with configured account ranks and API-key policies
- **WHEN** it upgrades to the integrated head
- **THEN** its rows and policy values remain intact and the upstream dashboard schema is available

#### Scenario: Upgrade an upstream beta5 database
- **GIVEN** a database at the upstream dashboard-timeout head
- **WHEN** it upgrades to the integrated head
- **THEN** existing rows remain intact and fork policy fields receive compatible defaults
- **AND** migration status reports one head
