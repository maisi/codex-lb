## MODIFIED Requirements

### Requirement: Limit warm-up persistence

The database SHALL persist global warm-up settings, per-account opt-in, warm-up attempt history, request-log source metadata, and a durable identity for each observed warm-up transition.

#### Scenario: Warm-up attempt is unique per transition
- **WHEN** an attempt is stored for an account, window, and observed transition
- **THEN** the database enforces uniqueness for that account/window/transition tuple
- **AND** the attempt separately retains the upstream reset timestamp

#### Scenario: Existing warm-up attempts are migrated
- **WHEN** an existing database is migrated to transition-based warm-up identity
- **THEN** every existing warm-up attempt receives a non-null legacy transition identity
- **AND** existing attempt history remains visible without being replayed

#### Scenario: Existing installs remain disabled
- **WHEN** an existing database is migrated
- **THEN** global warm-up is disabled
- **AND** all existing accounts remain opted out
- **AND** staggered idle warm-up is disabled

#### Scenario: Warm-up request logs remain separable from user traffic
- **WHEN** a warm-up request is logged
- **THEN** the request log records a source value that allows account usage summaries to exclude internal warm-up traffic
