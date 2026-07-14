## Context

The fork and upstream each added migrations after their last shared Alembic revision. The synchronized tree therefore contains two valid histories but no common descendant, so Alembic rejects the ambiguous `head` target. Existing deployments may be stamped anywhere along either history and must retain a forward-only upgrade path.

## Goals / Non-Goals

**Goals:**

- Restore one Alembic head without changing either merged migration history.
- Allow fresh databases and databases on either parent history to upgrade normally.
- Keep the synchronization revision schema-neutral.

**Non-Goals:**

- Reorder or rewrite existing migrations.
- Add, remove, or backfill schema objects in the merge revision.
- Change runtime migration locking or legacy revision remapping.

## Decisions

Add one no-op Alembic merge revision with both current heads in `down_revision`. This is Alembic's native representation for converging independent histories and lets it apply whichever parent path a database is missing before recording the common descendant.

Re-parenting the upstream model-registry migration was rejected because merged migration history is immutable and existing databases may already store that revision. Resetting the fork to upstream was rejected because it would discard fork-owned migrations and schema behavior.

## Risks / Trade-offs

- A later migration created from either old parent could recreate multiple heads. Mitigation: migration CI and `codex-lb-db check` require a single current head.
- Downgrading the merge revision intentionally exposes both parent heads again. Mitigation: treat downgrade as an operator-directed rollback step and upgrade to the merge revision before normal application startup.

## Migration Plan

1. Deploy the synchronized build containing both parent histories and the merge revision.
2. Run the normal serialized `upgrade head` path; Alembic applies any missing parent path and records the merge revision.
3. Verify `codex-lb-db check` reports one head and no schema drift.

Rollback requires downgrading from the merge revision to the appropriate parent history before deploying the corresponding older application build.

## Open Questions

None.
