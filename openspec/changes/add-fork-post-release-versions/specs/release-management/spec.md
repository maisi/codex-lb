# release-management — fork post-release versions

## ADDED Requirements

### Requirement: Fork releases extend a beta with post-release versions

The release tooling SHALL accept `X.Y.Z-beta.N.postM` (`M` ≥ 1) as a beta
version with tag `vX.Y.Z-beta.N.postM` and PEP 440 spelling `X.Y.ZbN.postM`.
Such a version SHALL order after `X.Y.Z-beta.N` and before
`X.Y.Z-beta.(N+1)`. Release preparation SHALL set every release-managed file to
the post-release version when given the base version, the beta number and the
post number, and the beta release guards and publish workflow SHALL treat a
`release/beta-X.Y.Z-beta.N.postM` pull request like any canonical beta release
pull request.

#### Scenario: fork release on top of an upstream beta

- **GIVEN** `main` carries `1.25.0-beta.9`
- **WHEN** release preparation runs with base version `1.25.0`, beta number `9`
  and post number `1`
- **THEN** every release-managed file contains `1.25.0-beta.9.post1`, and
  `uv.lock` may record `1.25.0b9.post1`
- **AND** a validated pull request from `release/beta-1.25.0-beta.9.post1`
  passes the beta release guard
- **AND** merging it creates tag `v1.25.0-beta.9.post1` and a GitHub prerelease

#### Scenario: upstream's next beta is newer than fork releases

- **GIVEN** tags `v1.25.0-beta.9`, `v1.25.0-beta.9.post1` and
  `v1.25.0-beta.9.post2`
- **WHEN** the latest beta of `1.25.0` is resolved
- **THEN** it is `v1.25.0-beta.9.post2`
- **AND** the next upstream beta number is `10`

### Requirement: Fork releases skip PyPI

When the Release workflow runs in a fork repository it SHALL NOT publish to
PyPI, SHALL still publish the Docker image, the Helm chart and the GitHub
release, and SHALL NOT list a PyPI install command in the release notes. The
Helm install command in the release notes SHALL name the publishing
repository's owner. A failure of any publishing job that does run SHALL still
withdraw the GitHub release.

#### Scenario: fork beta release without PyPI

- **GIVEN** the Release workflow runs for `v1.25.0-beta.9.post1` in a fork
- **WHEN** the Docker image and Helm chart publish successfully
- **THEN** the PyPI job is skipped
- **AND** the GitHub release is created with the build artifacts
- **AND** its notes contain the Docker and Helm install commands but no `uvx`
  command

## MODIFIED Requirements

### Requirement: Prerelease artifacts do not advance stable aliases

The release publishing workflow SHALL accept both stable tags (`vX.Y.Z`) and prerelease tags (`vX.Y.Z-alpha.N`, `vX.Y.Z-beta.N`, `vX.Y.Z-rc.N`, and the post-release form `vX.Y.Z-beta.N.postM`). For prerelease tags, Docker publishing SHALL NOT update `latest`, `X`, or `X.Y` aliases, and the GitHub Release SHALL remain marked as a prerelease and not latest. Stable tags SHALL retain existing stable aliases and latest-release behavior.

#### Scenario: beta release publishes beta-only Docker tags

- **GIVEN** release tag `v1.19.0-beta.1`
- **WHEN** the release publishing workflow builds the Docker image
- **THEN** it publishes the exact version tag `1.19.0-beta.1`
- **AND** it MAY publish channel tag `beta`
- **AND** it MUST NOT publish or update `latest`, `1`, or `1.19`

#### Scenario: post-release beta publishes beta-only Docker tags

- **GIVEN** release tag `v1.25.0-beta.9.post1`
- **WHEN** the release publishing workflow builds the Docker image
- **THEN** it publishes the exact version tag `1.25.0-beta.9.post1`
- **AND** it MAY publish channel tag `beta`
- **AND** it MUST NOT publish or update `latest`, `1`, or `1.25`
