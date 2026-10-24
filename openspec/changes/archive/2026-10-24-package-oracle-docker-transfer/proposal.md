## Why

Docker operators cannot use the complete SQLite-to-Oracle transfer or Oracle runtime with the current images because neither Dockerfile installs the optional Oracle driver. Provide the dependency in both images and an actionable container runbook using the existing data volume.

## What Changes

- Install the existing locked Oracle extra in standard and distroless images.
- Document a locally built image, stopped-source backup, direct CLI dry run/transfer, wallet/network continuity and application cutover.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `oracle-database`: Require both Docker images to include the native Thin driver and support direct migration CLI invocation.

## Impact

Two Docker dependency-install commands and the existing Oracle/database documentation. No runtime setting, new dependency version or default backend change.
