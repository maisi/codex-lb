## Purpose and decision

Support Docker operators of the complete transfer. Oracle is a runtime driver extra, already locked in the project; install it during both image builds because neither runtime image supplies an installer. SQLite remains zero-config.

## Example and operational constraints

Build `docker build -t codex-lb:oracle .` from this updated checkout. After stopping and backing up container `codex-lb`, run `docker run --rm --volumes-from codex-lb --env-file .env.oracle --entrypoint python codex-lb:oracle -m app.db.migrate migrate-to-oracle --source-sqlite /var/lib/codex-lb/store.db --dry-run`, then repeat without dry run. Keep the same data mounts and encryption key for application cutover.

`--volumes-from` does not inherit networks or environment. Add the necessary Docker network/wallet mount and preserve the original runtime configuration. A previously published image does not contain uncommitted checkout changes. A missing driver or older CLI is addressed by rebuilding the image, not modifying a running container.
