## ADDED Requirements

### Requirement: Fork synchronization verifies imported upstream release metadata

Fork pull requests importing an upstream release MUST pass beta metadata admission only when the official upstream release is an ancestor of the proposed merge and all release-managed version values match that release. Fork-authored release branches MUST continue requiring canonical release validation evidence. Missing upstream provenance or changed version values MUST NOT bypass ordinary beta release admission.

#### Scenario: Verified upstream release import
- **WHEN** a non-release branch on a fork contains the official upstream release commit and matching release-managed version values
- **THEN** beta metadata admission accepts the import without treating it as a new release

#### Scenario: Unverified or authored beta release
- **WHEN** upstream release ancestry is absent, version values differ, or the branch authors a release
- **THEN** ordinary beta release admission continues to apply
