## Context

The existing CLI owns database snapshotting, key/storage preflight, Oracle schema protection, atomic transfer and verification. Docker users need only host orchestration around it. The existing image runs startup migrations by default and a live SQLite process prevents transfer through its lifecycle lock.

## Goals / Non-Goals

Automate the host runbook with an explicit apply mode, complete data-directory backup and uniform connection mounts. Do not invent database-copy logic, execute a migration in this workspace, reproduce arbitrary Docker/Compose deployment settings, start the application, or create/print secrets.

## Decisions

- Use Bash arrays and direct Docker CLI subprocesses; no host Python dependency, `eval`, sourced environment or tracing. Pass secrets only through an existing environment file.
- Default to dry run, requiring an already stopped source. `--apply` explicitly permits stopping it, backing up and transferring; it always runs the database dry run first. An optional `--build` builds the repository image before downtime.
- Validate the daemon, source container, inherited data mount, image/CLI/driver and Oracle connectivity before stopping. Reject inherited application-code mounts that would hide the image. Inspect only mount destinations and running state, never environment values.
- Reserve a new private backup directory before stop. Copy the complete source data directory, including SQLite sidecars/key/archives, after stopping. Preserve partial backups and leave the source stopped on every later failure. External key/wallet backups remain operator-owned.
- Forward network and repeated mounts identically to all helper containers and print a quoted example cutover command. No automatic application start, rollback restart, target clearing or transfer retry occurs.

## Risks / Trade-offs

- Other workers or an external orchestrator can use/restart shared mounts; document stopping them and recheck source state around backup. The underlying database lifecycle/write locks remain authoritative.
- A failed/uncertain commit requires inspection; never automatically restart SQLite or retry.
- Docker/Oracle live environments may be unavailable locally; use an executable Docker stub to test real wrapper control flow and report live-test limits.
