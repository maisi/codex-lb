## Why

Merging upstream `main` into the fork combines two independently advanced Alembic histories. Without an explicit merge revision, `alembic upgrade head` fails because both the fork observability revision and the upstream model-registry revision remain heads.

## What Changes

- Add a no-op Alembic merge revision whose parents are the fork and upstream heads.
- Preserve both histories while restoring a single upgrade target for fresh and existing databases.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-migrations`: the synchronized fork exposes one Alembic head after combining the fork and upstream migration histories.

## Impact

- Migration: `app/db/alembic/versions/20260714_000000_merge_fork_and_model_registry_heads.py`
- Tests: existing migration graph, upgrade, downgrade, and drift suites
- Specs: `openspec/specs/database-migrations/spec.md`
