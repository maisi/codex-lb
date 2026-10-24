## Verification

- Both Python dependency stages use `uv sync --frozen --no-dev --no-install-project --extra oracle`, preserving their existing extras and startup commands.
- `uv tree --frozen --package oracledb` verifies locked driver 26.0.1 and its dependency closure; lockfile includes Python 3.14 wheels.
- Direct `python -m app.db.migrate migrate-to-oracle --help` succeeds and exposes source/key/batch/dry-run options.
- New change and synced Oracle capability pass strict OpenSpec validation; `git diff --check` passes.
- The documented one-shot command replaces application startup with the migration module and retains the stopped source mounts. Network/environment/wallet continuity and unpublished image status are explicit.
- Docker daemon socket access is denied in this environment. No image build, container run or production transfer was executed. This is a packaging/documentation change, so no new implementation-mirroring tests were added; existing transfer test results remain in the transfer change verification.
