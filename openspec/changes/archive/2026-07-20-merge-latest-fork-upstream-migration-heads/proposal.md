## Why

The refreshed upstream history added migrations after the fork's previous merge revision. Combining the histories therefore produces two Alembic heads again and makes `upgrade head` ambiguous until they share a new descendant.

## What Changes

- Add a no-op Alembic merge revision joining the current fork and upstream heads.
- Extend the migration convergence scenario to cover repeated upstream synchronizations after an earlier merge revision.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `database-migrations`: repeated fork/upstream synchronization continues to expose exactly one Alembic head.

## Impact

- Migration: `app/db/alembic/versions/20260720_000000_merge_fork_and_dashboard_index_heads.py`
- Tests: existing migration graph, upgrade, downgrade, and drift suites
- Specs: `openspec/specs/database-migrations/spec.md`
