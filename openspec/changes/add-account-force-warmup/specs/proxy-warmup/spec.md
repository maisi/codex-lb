## ADDED Requirements

### Requirement: Dashboard operators can force-warm one account
The system SHALL expose a dashboard-authenticated write action that runs the compact proxy warmup request for exactly one selected active account. The action MUST NOT select or warm any other account and MUST NOT invoke the usage-refresh-only Force probe path.

#### Scenario: Active account is warmed
- **WHEN** an authorized dashboard operator requests warmup for an active account
- **THEN** the system sends one compact proxy warmup request through that account
- **AND** returns a structured result identifying the selected account and warmup outcome

#### Scenario: Targeting bypasses usage eligibility only
- **WHEN** an authorized dashboard operator requests warmup for an active account that is not currently usage-eligible for scheduled warmup
- **THEN** the system still attempts the selected account's compact warmup request
- **AND** preserves credential, ownership, and transport validation

#### Scenario: Inactive account is rejected
- **WHEN** an authorized dashboard operator requests warmup for a disabled or paused account
- **THEN** the system rejects the action without sending an upstream warmup request

#### Scenario: Account does not exist
- **WHEN** an authorized dashboard operator requests warmup for an unknown account identifier
- **THEN** the system returns the standard account-not-found response
- **AND** sends no upstream warmup request

#### Scenario: Dashboard write access is required
- **WHEN** a caller without dashboard write access requests account warmup
- **THEN** the system rejects the request before credential acquisition or upstream traffic

### Requirement: Targeted warmup preserves proxy warmup invariants
The targeted account action MUST use the existing compact warmup request behavior, MUST classify its request log as warmup traffic, MUST exclude the request from ordinary usage accounting, and MUST support live token vending for a borrowed account.

#### Scenario: Warmup request is logged
- **WHEN** a targeted compact warmup attempt settles
- **THEN** the request log records the attempt as warmup traffic for the selected account
- **AND** records the model, latency, and success or structured failure outcome

#### Scenario: Borrowed account uses live token vending
- **WHEN** the selected active account is borrowed and requires live credential vending
- **THEN** the system obtains a live token through the existing vending path
- **AND** performs the compact warmup without requiring stored refresh credentials

#### Scenario: Warmup does not consume ordinary accounting
- **WHEN** a targeted compact warmup attempt completes
- **THEN** the system does not charge or settle the request as ordinary API-key usage
