## Why

Docker operators currently repeat a multi-command runbook to stop, back up and transfer SQLite state. A host-side script can execute the proven sequence consistently without copying credentials into shell commands or guessing application deployment options.

## What Changes

- Add an explicit Docker migration wrapper with a read-only target dry-run default and `--apply` for stop/backup/verified transfer/check.
- Accept an existing image or opt-in local build, environment file, source container/data/key paths, backup location, network and repeatable mounts.
- Refuse unsafe source mounts and backup overwrites; stop immediately on failure and never restart an installation automatically.
- Print the remaining application cutover command and document short usage in the owning runbook and database guide.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `oracle-database`: Define the Docker wrapper's source lifecycle, backup, mode, configuration and failure contracts.

## Impact

One Bash host script, subprocess-level tests with a fake Docker executable, and Oracle documentation/spec context. No database migration, dependency or runtime setting is added.
