## ADDED Requirements

### Requirement: API keys control prompt-cache continuation

Each API key SHALL persist a boolean prompt-cache continuation policy. Create requests that omit the policy and all historical keys MUST resolve it to false. Create, read, list, update, and regenerate flows MUST preserve and expose the value.

#### Scenario: Existing or omitted key remains disabled
- **WHEN** an existing API key is migrated or a key is created without the policy
- **THEN** prompt-cache continuation is false

#### Scenario: Policy round-trips
- **WHEN** an operator creates or updates an API key with prompt-cache continuation enabled
- **THEN** subsequent API reads and key regeneration preserve true
