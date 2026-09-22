## ADDED Requirements

### Requirement: Temporary quota unavailability preserves known model capabilities

Catalog refresh MUST preserve an existing account's last-known model and service-tier capability evidence while that account is temporarily rate-limited or quota-exhausted and its plan is unchanged. Temporary quota unavailability MUST NOT by itself be interpreted as model entitlement removal or bootstrap suppression. Retained capability evidence MUST NOT bypass request quota enforcement or hard continuity ownership.

Accounts without prior capability evidence MUST remain unknown rather than inherit another account's catalog. Account removal, administrative pause or deactivation, authentication-required state, plan changes, and fresh authoritative catalog omissions MUST retain their existing exclusion behavior. Persisted catalog snapshots MUST preserve the same capability interpretation across replicas and restart.

#### Scenario: All advertisers of a plan exhaust quota
- **GIVEN** known Plus accounts advertise a model and a different-plan account still has quota
- **WHEN** the Plus accounts exhaust quota and catalog refresh runs
- **THEN** their known model capabilities remain available to continuity eligibility checks
- **AND** exhausted owners cannot serve requests or cause unchanged owner-bound requests to move to a sibling
- **AND** a required exhausted owner is reported as unavailable rather than outside model policy

#### Scenario: Every account is temporarily unavailable
- **GIVEN** all known accounts are temporarily rate-limited or quota-exhausted
- **WHEN** catalog refresh has no active upstream fetch candidate
- **THEN** previously known capabilities for unchanged plans remain intact
- **AND** an account with no prior catalog remains unknown

#### Scenario: Quota resets and the owner recovers
- **GIVEN** an owner's capability evidence was retained during quota exhaustion
- **WHEN** its quota resets and it is otherwise eligible
- **THEN** its continuation can use its known capabilities without waiting for another catalog refresh

#### Scenario: Genuine capability removal remains authoritative
- **GIVEN** an account previously advertised a model
- **WHEN** the account is removed, administratively disabled, requires authentication, changes plan, or freshly reports that the model is absent
- **THEN** temporary-quota retention does not preserve obsolete capability access

#### Scenario: Retained capabilities survive snapshot replication
- **GIVEN** the leader retained known capabilities for a quota-exhausted account
- **WHEN** another replica loads the persisted catalog snapshot
- **THEN** both replicas preserve the same capability membership and still enforce quota restrictions
