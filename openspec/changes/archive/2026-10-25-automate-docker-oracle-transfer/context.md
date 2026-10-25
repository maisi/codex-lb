## Purpose and scope

Provide a short host-side entry point for the existing Docker runbook while retaining the database CLI as the only transfer implementation. The user's source container is `codex-lb`, matching the default. The script itself does not run a production migration during development.

## Example

With a protected `.env.oracle` containing the Oracle URL and preserved runtime settings, run `bash scripts/migrate-sqlite-to-oracle-docker.sh --env-file .env.oracle --build --apply`. Existing updated images can omit `--build`. The source is stopped only after image/connection preflight, and the resulting backup is retained for acceptance.

## Decisions and constraints

Default dry run requires a stopped source and neither stops nor backs up it. Apply reserves a new private backup directory, stops/copies the source and runs the existing dry-run/transfer/check. Bash arrays pass environment paths, network and repeated mounts without evaluation. Application startup stays separate because a general wrapper cannot reproduce arbitrary ports/network/Compose deployment configuration.

## Failures and operations

The script rejects inherited code mounts and missing data mounts before downtime. It leaves the source stopped after later errors, retains partial backups, and never retries uncertain commits or restarts an application. External keys/wallets require their own backups; other workers/orchestrators must remain stopped. See the owning runbook/context for stable operational detail and verification.md for evidence.
