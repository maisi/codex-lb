## ADDED Requirements

### Requirement: Routing trace quota percentages exclude local load

Routing traces MUST report normalized observed quota usage in their primary and
secondary used-percent fields. In-flight request counts and reserved tokens
MUST NOT be serialized as consumed quota. With unchanged usage observations,
acquiring or releasing a lease MUST NOT change those fields or their
quota-threshold classification. Unknown windows MUST remain null.

#### Scenario: Request details remain stable during concurrent requests

- **GIVEN** an available account reports 8% primary and 15% secondary usage
- **WHEN** an operator reads routing decisions made before, during, and after a concurrent 160000-token lease
- **THEN** the routing API reports 8% and 15% for that account in every decision
- **AND** the account remains below the configured 90% quota threshold

#### Scenario: Weekly-only accounts retain an unknown primary window

- **GIVEN** an account reports only a secondary quota window
- **WHEN** it holds a lease and a routing decision is recorded
- **THEN** the primary used-percent field remains null
- **AND** the secondary field contains normalized observed secondary usage
