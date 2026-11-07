## ADDED Requirements

### Requirement: Guardian refresh releases connections during slow work

Auth Guardian MUST release selection and eligibility-read connections before refreshing credentials. Its owned refresh MUST use short-lived persistence operations and MUST NOT retain a database connection across peer-claim polling, refresh-admission waits, or upstream OAuth I/O. Cancellation MUST still await started token rotations through persistence and claim release, and one account's refresh failure MUST NOT prevent other selected accounts from completing.

#### Scenario: Three concurrent refreshes use a four-connection pool

- **GIVEN** the default three guardian workers and a four-connection background pool with zero overflow
- **WHEN** selected accounts wait for slow upstream OAuth responses
- **THEN** no guardian connection remains checked out during those waits
- **AND** background queries and refresh-claim operations can complete before the upstream responses arrive

#### Scenario: A peer owns a refresh claim

- **WHEN** a guardian refresh waits between attempts to acquire a peer-owned claim
- **THEN** its freshness-read connection is returned before the polling delay
- **AND** a peer's committed rotation is adopted without another upstream exchange

#### Scenario: Cancellation and partial failure preserve settlement

- **GIVEN** multiple guardian token exchanges have started
- **WHEN** the pass is cancelled and one exchange fails
- **THEN** started successful rotations are persisted and owned claims are released before cancellation finishes
- **AND** all owned database sessions are closed
