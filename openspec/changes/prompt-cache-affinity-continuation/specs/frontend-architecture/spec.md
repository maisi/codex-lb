## ADDED Requirements

### Requirement: Dashboard exposes the per-key continuation policy

The API-key create and edit dialogs SHALL expose a clearly described prompt-cache continuation boolean. The create control MUST default to off, and edit MUST reflect and persist the stored value.

#### Scenario: Create dialog opens
- **WHEN** an operator opens the API-key create dialog
- **THEN** prompt-cache continuation is unchecked

#### Scenario: Enabled key is edited
- **WHEN** an operator opens an API key whose policy is true
- **THEN** the control is checked and submitted edits preserve the selected value

### Requirement: Dashboard labels cache metric semantics

The Reports dashboard SHALL label total input, cached input, and cache-hit ratio as provider-reported logged usage and SHALL state that cached input is included in total input.

#### Scenario: Cache metrics render
- **WHEN** report usage contains cached input
- **THEN** the UI shows the cached amount and ratio without presenting cached input as additional tokens or inferred savings
