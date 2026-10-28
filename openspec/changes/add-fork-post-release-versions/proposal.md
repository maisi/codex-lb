## Why

The fork ships its own fixes and features on top of the upstream beta train,
but its release-managed files still say `1.25.0-beta.9`, the version of the
last upstream beta it merged. Deployments cannot tell fork builds apart, and
there is no versioned image to roll back to, only the rolling `main` / `sha-`
tags.

Numbering fork builds `1.25.0-beta.10`, `beta.11`, … would collide with the
betas upstream publishes next: two different `beta.10`s, and a version-file
conflict on every sync once upstream resumes.

## What Changes

- Release tooling accepts a post-release of a beta, `X.Y.Z-beta.N.postM`
  (tag `vX.Y.Z-beta.N.postM`, PEP 440 `X.Y.ZbN.postM`). It sorts after
  `beta.N` and before `beta.N+1` in both semver and PEP 440, so the fork's
  releases never collide with upstream's and the next upstream beta is always
  newer.
- `scripts.prepare_beta_release --post-number M` (with `--base-version` and
  `--beta-number`) sets the release-managed files to that version.
- The beta release guards, the publish workflow and release metadata treat a
  `release/beta-X.Y.Z-beta.N.postM` PR like any canonical beta PR: validation
  evidence, `vX.Y.Z-beta.N.postM` tag, GitHub prerelease.
- In a fork, the Release workflow skips PyPI (the package name belongs to
  upstream) and still publishes the Docker image, Helm chart and GitHub
  release; the release notes omit the PyPI install line. The Helm install line
  uses the publishing repository's owner instead of a hard-coded one.
- The beta changelog keeps one line per commit: every commit after the first
  used to carry `git log`'s record newline inside its short SHA.

## Capabilities

### Modified Capabilities

- `release-management`: post-release beta versions for fork releases; fork
  releases skip PyPI.

## Impact

- Release scripts, `release.yml`, unit tests. No application, schema or
  setting change; the dashboard update check already compares semver
  prereleases generically.
- Upstream's own flow is unchanged: release-please and the automated beta PR
  never produce a post version.
