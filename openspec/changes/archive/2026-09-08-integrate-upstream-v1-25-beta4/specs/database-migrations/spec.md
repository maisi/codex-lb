## ADDED Requirements

### Requirement: Integrated upstream and fork database upgrades preserve fork data

Database upgrades MUST converge to one migration head from the pre-integration fork and upstream heads, preserving account credentials, API-key account ranks, forced-usage flags and continuation settings. Deployed migration revision identities MUST remain valid.

#### Scenario: Existing fork database upgrades
- **WHEN** a database at the pre-integration fork head upgrades to the integrated head
- **THEN** its fork settings and account assignments remain unchanged and upstream schema additions are available

#### Scenario: Existing upstream database upgrades
- **WHEN** a database at the upstream v1.25.0-beta.4 head upgrades to the integrated head
- **THEN** fork fields receive compatible defaults and migration status reports one head
