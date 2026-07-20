## Context

The prior fork merge revision joined the histories known at that synchronization point. Upstream subsequently advanced its own migration line, so the next Git merge again combines two valid heads. Existing databases may be stamped on either line.

## Goals / Non-Goals

**Goals:**

- Restore one Alembic head without rewriting either parent history.
- Preserve upgrades from fresh databases and either current parent.

**Non-Goals:**

- Apply schema changes in the merge revision.
- Re-parent or delete previously published revisions.

## Decisions

Add another schema-neutral Alembic merge revision with the current fork merge head and upstream dashboard-index head as parents. Repeated merge revisions are the expected Alembic representation when independently advancing histories synchronize more than once.

## Risks / Trade-offs

- Future upstream migrations can create another parallel head after this synchronization. Mitigation: every sync verifies the graph and adds a new merge revision when required.
- Downgrading the merge revision exposes its two parents. Mitigation: normal deployments only upgrade to the single head.

## Migration Plan

Deploy the synchronized build and run the normal serialized `upgrade head` path. Alembic applies whichever parent path is missing and records the common merge revision.

## Open Questions

None.
