## ADDED Requirements

### Requirement: Beta6 upstream additions retain fork migration and account policy

Upgrading the integrated beta5 fork or the new upstream beta6 schema MUST converge to one head while preserving account credentials, API-key ranks, forced usage and continuation flags. New report aggregates and dashboard routing fields MUST follow their upstream migration defaults. Deployed revision identities MUST remain valid.

#### Scenario: Existing fork upgrades through beta6 additions
- **GIVEN** a beta5 fork database with account assignments and per-key policy
- **WHEN** it upgrades to the beta6 integrated head
- **THEN** policy values remain intact and upstream report/routing schema is available

#### Scenario: Upstream database receives fork defaults
- **WHEN** a database at the new upstream head upgrades to the integrated head
- **THEN** existing rows remain intact and fork fields receive compatible defaults
- **AND** Alembic reports one head
