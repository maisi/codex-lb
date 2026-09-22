## ADDED Requirements

### Requirement: Beta9 fork integration preserves deployed migration histories

The integrated beta9 fork MUST provide a single Alembic head reachable from the deployed beta6 fork and upstream beta9 migration histories. Integration MUST NOT rewrite deployed revision identifiers or their parent relationships. Any merge revision MUST perform no schema or data operations. Upgrades MUST preserve existing accounts, credentials, ranked API-key assignments, continuation policies, and fork configuration while applying missing schema changes.

#### Scenario: Upgrade a populated beta6 fork database
- **GIVEN** a deployed beta6 fork database with account priorities and API-key continuation settings
- **WHEN** it upgrades to the integrated beta9 head
- **THEN** existing policy values and records remain intact
- **AND** migration status reports one head with all imported schema additions

#### Scenario: Upgrade an upstream beta9 database
- **GIVEN** a database at the upstream beta9 migration heads
- **WHEN** it upgrades to the integrated fork head
- **THEN** existing records remain intact and missing fork fields receive compatible defaults
- **AND** migration status reports one head

#### Scenario: Imported migration lineage has an explicit convergence
- **GIVEN** the imported release continues an ancestor of the fork's deployed migration head
- **WHEN** a no-op merge revision explicitly joins the imported lineage to that fork head
- **THEN** topology validation accepts the converged history without rewriting released migrations
- **AND** a divergent lineage without that explicit convergence still fails validation
