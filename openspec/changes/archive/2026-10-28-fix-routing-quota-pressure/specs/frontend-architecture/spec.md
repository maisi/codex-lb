## MODIFIED Requirements

### Requirement: Sticky thresholds are presented in percent used with a remaining equivalent

The sticky reallocation threshold controls SHALL name the quota window they
apply to, SHALL state that the value is percent used, and SHALL show the
quota-arithmetic remaining percent for a valid threshold value. The explanation
SHALL distinguish observed quota usage from local load weighting: in-flight
work MUST NOT be described as additional consumed quota or as independently
triggering a quota threshold.

#### Scenario: Threshold unit hint

- **GIVEN** the sticky secondary threshold input holds the valid value `70`
- **WHEN** the routing settings section renders
- **THEN** a hint shows `70% used` alongside `30% remaining` in quota terms
- **AND** the quota-window explainer states that in-flight work affects weighted selection independently of quota usage

#### Scenario: Quota window explainer

- **WHEN** the routing settings section renders
- **THEN** an explainer identifies primary quota as the 5-hour window and secondary quota as the longer weekly window (monthly on plans without a weekly window)
- **AND** it states that account pages show percent remaining while the thresholds are percent used
