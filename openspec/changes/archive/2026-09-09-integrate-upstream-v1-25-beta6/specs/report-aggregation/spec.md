## ADDED Requirements

### Requirement: Fork API-key report filters survive aggregation
The report options endpoint MUST expose API-key identities and available names from scoped report history, including folded history after raw-log pruning. The dashboard MUST retain API-key filter selection and show a deleted key by its ID. Options queries MUST avoid report measures and speed calculations.

#### Scenario: Historical key survives pruning
- **WHEN** report history is folded and raw logs are pruned
- **THEN** the report options retain the historical API key and cache usage remains unchanged
