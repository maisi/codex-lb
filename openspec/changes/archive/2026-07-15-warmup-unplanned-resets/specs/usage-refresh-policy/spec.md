## MODIFIED Requirements

### Requirement: Reset-confirmed limit warm-up

The system SHALL support an optional limit warm-up mechanism that is disabled by default. When enabled globally and for an account, background usage refresh MAY send one minimal upstream Responses request after it confirms that a selected quota window has moved from an exhausted sample to a newly available reset window. Reset confirmation SHALL be based on the observed usage transition and SHALL NOT require the new reset deadline to be later than the exhausted sample's deadline.

#### Scenario: Warm-up follows a scheduled reset
- **GIVEN** limit warm-up is enabled globally and for an account
- **AND** the account's previous usage sample for a selected window was exhausted
- **WHEN** background usage refresh records a newer available sample for that window with a later `reset_at`
- **THEN** the system sends at most one warm-up request for that observed transition

#### Scenario: Warm-up follows an unplanned reset
- **GIVEN** limit warm-up is enabled globally and for an account
- **AND** the account's previous usage sample for a selected window was exhausted
- **WHEN** background usage refresh records a newer available sample whose `reset_at` is unchanged or earlier
- **THEN** the system sends at most one warm-up request for that observed transition
- **AND** a prior attempt for a different transition with the same account, window, and `reset_at` MUST NOT suppress the new attempt

#### Scenario: Warm-up is opt-in and safe by default
- **GIVEN** background usage refresh is preparing to evaluate limit warm-up candidates
- **WHEN** global limit warm-up is disabled
- **OR** the account is not opted in
- **THEN** background usage refresh MUST NOT send warm-up traffic

#### Scenario: Warm-up uses fresh opt-in state after usage refresh
- **GIVEN** an account was loaded before a background usage refresh cycle
- **AND** the account's limit warm-up opt-in changes while the refresh cycle is running
- **WHEN** the scheduler evaluates warm-up candidates after writing usage samples
- **THEN** the scheduler MUST evaluate the latest persisted opt-in value rather than the stale in-session account object

#### Scenario: Warm-up respects unsafe account states
- **WHEN** an account is paused, deactivated, rate-limited, quota-exceeded, or in an auth-refresh failure path
- **THEN** limit warm-up MUST NOT send traffic for that account

#### Scenario: Warm-up attempts are durable and deduplicated
- **WHEN** multiple refresh workers observe the same exhausted-to-available transition
- **THEN** the database permits at most one persisted attempt for that account/window/transition tuple
- **AND** later refresh cycles skip that transition after a prior attempt exists

#### Scenario: Staggered idle warm-up pre-starts rolling primary windows
- **GIVEN** limit warm-up and staggered idle warm-up are enabled globally
- **AND** multiple active accounts are opted into limit warm-up
- **AND** an opted-in account has a healthy idle primary 5h usage sample
- **WHEN** background usage refresh evaluates that account inside its deterministic stagger slot
- **THEN** the system MAY send one minimal upstream warm-up request for that account's current 300-minute cycle
- **AND** the system MUST NOT send another staggered idle warm-up for that same account/cycle tuple
- **AND** account slots MUST be spread deterministically across the 300-minute rolling window so restarts do not align all opted-in accounts into the same phase

#### Scenario: Staggered idle warm-up remains opt-in
- **GIVEN** limit warm-up is enabled globally and for an account
- **AND** staggered idle warm-up is disabled
- **WHEN** background usage refresh observes an idle primary 5h sample that is not a reset-confirmed transition
- **THEN** limit warm-up MUST NOT send synthetic traffic for that idle sample
