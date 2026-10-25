## ADDED Requirements

### Requirement: Docker images include the Oracle driver and direct transfer CLI

Both standard and distroless Docker images SHALL install the existing locked Oracle extra so their Python interpreter can load the native Thin driver. Operators MUST be able to invoke the migration CLI directly without running application startup or installing packages at runtime. SQLite MUST remain the default backend. Container transfer documentation MUST retain the stopped source volume, key and archives and identify required target environment, wallet and network configuration.

#### Scenario: A Docker operator performs a dry run
- **WHEN** a newly built image runs `python -m app.db.migrate migrate-to-oracle --source-sqlite PATH --dry-run` directly against the stopped source volume
- **THEN** the Oracle driver is available without runtime package installation
- **AND** the normal application startup command does not run before the dry run
