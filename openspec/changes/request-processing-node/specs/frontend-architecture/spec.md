# Spec Delta

## ADDED Requirements

### Requirement: Request list and details show processing node compactly
The existing request list and request details MUST display the processing-node label with a localized Unknown fallback for null or absent `processingNode`. The frontend schema MUST accept responses from older backends that omit the field. The display MUST use existing request surfaces without adding navigation.

#### Scenario: Operator sees execution owner
- **WHEN** a request entry has processingNode `home-b`
- **THEN** its list row and opened details display `home-b` as the processing node

#### Scenario: Older backend and historical record remain readable
- **WHEN** processingNode is absent or null
- **THEN** the request row and details render localized Unknown without failing schema validation
