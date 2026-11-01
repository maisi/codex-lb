# Spec Delta

## ADDED Requirements

### Requirement: Oracle processing-node storage evolves its dedicated lineage
Oracle MUST receive nullable 64-byte processing-node storage through an additive revision after its immutable baseline. The frozen baseline MUST remain unchanged. Model drift checks and SQLite transfer target validation MUST use the evolved Oracle schema contract. No historical row backfill or new index MUST be required.

#### Scenario: Oracle schema is inspected offline
- **WHEN** the evolved model and dedicated migration lineage are inspected without a live database
- **THEN** processing-node storage is nullable VARCHAR2(64 BYTE) with no default
- **AND** the immutable baseline remains independently verifiable
