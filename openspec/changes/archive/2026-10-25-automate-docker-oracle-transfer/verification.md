## Verification

- **24 subprocess tests passed** against an executable Docker stub. Coverage includes apply ordering, image/connection/copy/dry-run/transfer/check failures, running/stopped source behavior, existing-backup protection, full data-directory assets, source restart detection, inherited mount guards, option errors, database backup coverage, exact network/repeated-mount/key/path forwarding, no shell evaluation or environment-content output, and no application start/retry.
- Wrapper and runbook pass `bash -n`. Shellcheck is not installed.
- `make lint` passed repository-wide architecture/settings/migration topology/Ruff checks; repository-wide `ty check` passed.
- Strict change and synced owning capability validation passed. Global `openspec validate --specs` still reports 18 pre-existing specs lacking SHALL/MUST; every failed file is unchanged by this work.
- Requirements map directly to the script mode parser, preflight/mount guard, private backup reservation, ordered existing CLI calls, EXIT diagnostics and printed cutover command. The change adds no DB revision, runtime setting or dependency.
- No real Docker/Oracle migration or application lifecycle action was executed. The wrapper tests replace Docker completely; earlier live-acceptance limits for the underlying transfer remain in force.
