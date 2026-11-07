## ADDED Requirements

### Requirement: Runtime images apply zlib security updates

The Debian 13 runtime image used by CI and release Trivy scans MUST upgrade
zlib1g from its configured Debian archives and MUST contain version
`1:1.3.dfsg+really1.3.1-1+deb13u1` or newer under Debian version ordering. The
build MUST fail if the installed package is missing or older than this floor.
The distroless image MUST upgrade its Debian 12 zlib1g before staging the
shared libraries copied into its runtime. The CI Trivy gate MUST continue
rejecting fixed HIGH and CRITICAL findings without suppressing CVE-2026-76844
or CVE-2026-85091.

#### Scenario: Base image contains the vulnerable Debian 13 package

- **GIVEN** the base image contains zlib1g `1:1.3.dfsg+really1.3.1-1+b1`
- **WHEN** the runtime image builds with the fixed package available
- **THEN** the final runtime contains at least the fixed version

#### Scenario: Fixed or newer package is installed

- **WHEN** the installed zlib1g equals or exceeds the fixed Debian 13 version
- **THEN** the build's zlib version check succeeds

#### Scenario: Package remains vulnerable or is absent

- **WHEN** the installed zlib1g is older than the floor or cannot be queried
- **THEN** the build's zlib version check fails

#### Scenario: Distroless copies updated Debian 12 libraries

- **WHEN** the distroless image stages libraries from its Debian 12 build stage
- **THEN** zlib1g has been upgraded using that stage's configured Debian archives
- **AND** the runtime copies those staged libraries
