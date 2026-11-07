## Context

See [proposal.md](proposal.md) for the CI finding. CI and release Trivy scans
build `Dockerfile`; rolling main builds use the same file. Its final stage
already updates selected packages with apt. `Dockerfile.distroless` instead
copies Debian 12 shared libraries from `python-build` into a shell-less runtime.

## Goals / Non-Goals

Use the existing apt transactions and distribution security archives. Keep
Trivy enforcement, base-image families, and application dependencies unchanged.

## Decisions

- Add zlib1g to both existing `--only-upgrade` lists, in the standard runtime
  and the distroless library-source stage respectively. Updating only a
  standard builder would leave the final image's vulnerable package intact.
- Compare the standard runtime's installed package version with the known
  Debian 13 fix using `dpkg --compare-versions` in the same apt `RUN` chain.
  A lower bound allows later security revisions; an exact version pin would
  break when the archive replaces that revision. For example, the reported
  `-1+b1` fails while `-1+deb13u1` and `-1+deb13u2` pass.
- Keep Debian 12's own package line for distroless. Applying a Debian 13
  version floor or mixing Debian releases there would be incorrect.
- Test the actual Dockerfile assertion with the real Debian comparator and a
  stub package query, alongside package-list and library-copy checks.

## Risks / Trade-offs

- A stale or unavailable security archive makes the standard build fail;
  it cannot silently ship the reported vulnerable version.
- Docker builds and image Trivy scans cannot run in this sandbox. Local checks
  verify package selection, staging order, and the executable version guard;
  CI still needs to validate archive availability and final image contents.
- Debian 12's fixed revision is not established by the Debian 13 finding.
  Distroless refreshes its distribution's zlib without claiming that the
  Debian 13 floor verifies Debian 12.
