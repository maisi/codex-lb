## MODIFIED Requirements

### Requirement: Fork and upstream migration histories converge on one head

When an upstream synchronization combines independently advanced fork and upstream Alembic histories, the synchronized migration graph MUST join the resulting heads with a no-op merge revision. The merge revision MUST preserve both parent histories and MUST restore exactly one valid `head` target without applying additional schema changes. A later synchronization that advances upstream beyond an earlier fork merge revision MUST add a new merge revision rather than re-parenting or deleting published history.

#### Scenario: Fresh database upgrades through both histories

- **WHEN** a fresh database upgrades to `head` after the upstream synchronization
- **THEN** Alembic applies both parent histories
- **AND** finishes at the single merge revision

#### Scenario: Database already at either parent upgrades safely

- **GIVEN** a database is already stamped at either parent revision
- **WHEN** it upgrades to `head`
- **THEN** Alembic applies the missing parent history as needed
- **AND** records the merge revision without dropping or rewriting schema objects

#### Scenario: Upstream advances after an earlier fork merge revision

- **GIVEN** the fork history already contains a published merge revision from an earlier synchronization
- **AND** upstream adds migrations on its own descendant line
- **WHEN** the histories synchronize again
- **THEN** the graph adds another no-op merge revision joining the current heads
- **AND** previously published revisions remain unchanged
