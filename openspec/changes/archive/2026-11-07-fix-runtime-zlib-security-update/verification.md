# Verification: fix-runtime-zlib-security-update

## Completeness and correctness

The added github-automation requirement is implemented and synced to the main
spec, with rationale and examples in its context document.

- `Dockerfile` upgrades zlib1g in its final runtime's apt transaction and
  compares the installed version with the Debian 13 security floor before
  removing apt lists. Later stages do not replace that runtime library.
- `Dockerfile.distroless` upgrades its Debian 12 zlib1g before staging the
  shared libraries copied into the final runtime.
- Security tests check both package lists and distroless staging/copy order.
  They execute the actual Dockerfile guard with real `dpkg` version ordering
  and a stub package query: vulnerable base/rebuild and missing versions fail;
  fixed, fixed rebuild, and newer security versions pass. The eight security
  cases failed against the original Dockerfiles and pass after the changes.
- CI and release scans both build `Dockerfile`; rolling main builds use it
  too. Distroless is not currently built or scanned by these workflows. The
  CI HIGH/CRITICAL gate and all Trivy configuration remain unchanged.

The implementation follows the existing apt upgrade/cleanup pattern and adds
no configuration, dependency changes, or scanner exceptions.

## Checks

- `make lint`: passed, including architecture and migration topology checks.
- `uv run --extra oracle ty check`: passed.
- `uv run --extra oracle pytest -q --tb=short tests/unit/test_docker_security.py tests/unit/test_native_egress_packaging.py tests/unit/test_github_ci_scripts.py`: 36 passed.
- `npx --yes @fission-ai/openspec@1.11.0 validate fix-runtime-zlib-security-update --strict`: passed.
- `npx --yes @fission-ai/openspec@1.11.0 validate --specs --strict`: 68 passed.
- `git diff --check`: passed.

Checks used a writable temporary uv cache because the default cache is
read-only in the sandbox. OpenSpec used the preinstalled 1.11.0 package.

## Verification limits

Docker builds and image Trivy scans cannot run in this sandbox. Debian archive
availability and final image contents therefore still need CI verification.
The runtime guard makes a successful standard image build contingent on the
installed zlib1g meeting the fixed Debian 13 version; a stale archive cannot
silently produce an image with the reported vulnerable package. Debian 12's
fixed revision is not established by this finding and is not asserted.

No critical implementation findings remain. Local implementation verification
is complete, with image build/scan verification explicitly pending CI.
