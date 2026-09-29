## ADDED Requirements

### Requirement: Post-beta9 upstream integration preserves deployed migration histories

The fork integration of upstream changes after `v1.25.0-beta.9` MUST provide a single Alembic head reachable from the deployed fork beta9 merge head and the upstream post-beta9 head. Integration MUST NOT rewrite deployed revision identifiers or their parent relationships, and the merge revision MUST perform no schema or data operations.

#### Scenario: Upgrade a populated fork database
- **GIVEN** a deployed fork database with account priorities and API-key continuation settings
- **WHEN** it upgrades to the integrated head
- **THEN** existing policy values and records remain intact
- **AND** migration status reports one head

#### Scenario: Downgrade from the integrated head to the fork beta6 merge
- **GIVEN** a database at the integrated head
- **WHEN** it downgrades to the fork beta6 merge revision
- **THEN** the fork beta6 merge and the upstream post-beta9 head remain stamped
- **AND** upgrading again restores the single head without repeating either parent's operations
