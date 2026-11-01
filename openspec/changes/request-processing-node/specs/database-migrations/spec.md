# Spec Delta

## ADDED Requirements

### Requirement: Processing-node storage is additive and preserves unknown history
The request-log schema MUST add nullable `processing_node` string storage of at most 64 characters with no server default or index. The migration MUST descend from the current intended single head, MUST NOT backfill or scan historical rows, and MUST preserve historical null values. Downgrade MUST remove only the added column.

#### Scenario: Existing and new rows coexist
- **WHEN** an existing database upgrades and new attributed rows are written
- **THEN** historical rows retain null and new rows retain their supplied label
- **AND** the migration graph has exactly one head

#### Scenario: Downgrade preserves request history
- **WHEN** the processing-node revision is downgraded to its parent
- **THEN** only the processing-node column is removed and existing request rows survive

#### Scenario: Existing model-created schema can replay migration history
- **WHEN** startup upgrades a ledgerless or previously stamped schema that already has the compatible processing-node column
- **THEN** the migration leaves that column and its values intact without adding it twice
