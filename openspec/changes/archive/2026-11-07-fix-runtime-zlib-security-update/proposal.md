## Why

CI run 42381574349 (2026-11-07, commit 81f345800) builds the image but fails
Trivy's HIGH gate on zlib1g CVE-2026-76844 and CVE-2026-85091. Debian 13 fixes
both in `1:1.3.dfsg+really1.3.1-1+deb13u1`, newer than the base image's package.

## What Changes

- Upgrade zlib1g with the existing runtime apt security updates and fail the
  standard image build when its installed version is below the Debian 13 fix.
- Upgrade the Debian 12 zlib1g in the distroless library-source stage before
  copying its shared libraries into the final image.
- Cover package selection and the version check with container security tests;
  preserve the existing Trivy scans and severity gate.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `github-automation`: Require scanned runtime images to carry the fixed
  Debian 13 zlib1g and refresh zlib in the distroless library-source stage.

## Impact

`Dockerfile`, `Dockerfile.distroless`, container security tests, and OpenSpec
documentation. CI and release scans both consume `Dockerfile`; distroless is
not currently built or scanned by the workflows. No Trivy exclusions, new
settings, application dependencies, or application behavior changes.
