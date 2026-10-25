## ADDED Requirements

### Requirement: Docker transfer wrapper defaults to non-mutating target preflight

The repository SHALL provide a host-side Docker transfer script. Its default and `--dry-run` mode MUST require a stopped source and run only image/connection checks and the existing transfer dry run; they MUST NOT stop/start application containers, create a backup, or perform target schema/data/sequence changes. `--apply` MUST explicitly select the stop/backup/transfer workflow. `--build` MUST be opt-in. Conflicting modes, missing option values and missing environment files MUST fail before application or database changes.

#### Scenario: Default preflight is invoked against a running source
- **WHEN** the wrapper is invoked without apply and the source is running
- **THEN** it reports that the source must be stopped or apply selected
- **AND** no source stop, backup, transfer or application start occurs

### Requirement: Docker transfer wrapper validates and backs up before applying

The wrapper MUST validate source mount coverage, reject inherited mounts that hide application code, and verify image/CLI/driver and Oracle connectivity before stopping a running source. Apply MUST reserve a new private backup directory without overwriting existing paths, stop the source, and copy its complete configured data directory before invoking the existing dry-run, transfer and schema check in that order. It MUST fail when the source is running during backup checks. Filesystem encryption keys/archives in that directory MUST be preserved in the backup. Additional external key/wallet backups SHALL remain explicitly documented operator responsibilities.

#### Scenario: Preflight or backup fails
- **WHEN** image/connection preflight, backup creation or copying fails
- **THEN** transfer does not run
- **AND** preflight failure leaves the original running state unchanged

#### Scenario: A destination backup already exists
- **WHEN** apply selects an existing backup path
- **THEN** it refuses that path before stopping the source
- **AND** existing backup contents remain unchanged

### Requirement: Docker transfer wrapper preserves helper configuration and failure ownership

The wrapper SHALL accept source container, image, environment file, source data/database/key paths, backup directory, Docker network and repeatable mount options. The selected SQLite database MUST be inside the backed-up data directory. Every helper MUST bypass startup with the Python entrypoint and receive the same mounts/environment/network. Argument boundaries MUST survive whitespace and shell metacharacters without evaluation. The wrapper MUST NOT source or print environment contents. Copy, dry-run, transfer or check failures MUST stop subsequent stages and MUST NOT restart the source, retry transfer, clear the target or start an application. Success MUST identify the retained backup and provide a separate, quoted cutover example that preserves helper connection configuration and explains adapting original deployment options.

#### Scenario: Transfer fails after source stop
- **WHEN** the existing CLI fails during dry-run, transfer or final schema checking
- **THEN** the script exits unsuccessfully and leaves retained backups available
- **AND** it does not automatically restart or retry either installation

#### Scenario: Wallet and network paths include whitespace or shell syntax
- **WHEN** an operator supplies network, mount, environment or key arguments containing such characters
- **THEN** helpers receive their exact arguments without shell evaluation
- **AND** environment-file contents do not appear in wrapper output
