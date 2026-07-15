## Context

Reset-confirmed warm-up currently recognizes only transitions where an exhausted usage sample is followed by available usage and a strictly later `reset_at`. Attempts are uniquely keyed by account, window, and that deadline. Both assumptions model scheduled rolling-window resets, but upstream can replenish weekly quota outside the expected schedule and can keep or move the deadline earlier.

The usage refresh path already provides durable before/after `UsageHistory` rows. The newly available row is therefore a stable identity for the observed transition, independent of the upstream deadline.

## Goals / Non-Goals

**Goals:**

- Warm selected quota windows whenever refresh observes an exhausted-to-available transition, including unchanged or earlier deadlines.
- Deduplicate concurrent evaluation of the same transition without suppressing a later unplanned transition that shares a deadline.
- Preserve the actual upstream `reset_at` value in dashboard-visible attempt history.
- Migrate existing attempts without replaying them.

**Non-Goals:**

- Inferring resets without an exhausted-to-available usage transition.
- Changing warm-up opt-in, thresholds, cooldown, model selection, or account safety policy.
- Changing staggered idle warm-up timing.

## Decisions

### Key reset-confirmed attempts by the available usage row

Add a non-null `transition_key` to warm-up attempts. Reset-confirmed candidates use `usage-history:<after-row-id>`; staggered idle candidates use `reset:<reset_at>` because they remain one-per-cycle rather than transition-driven. The database unique constraint becomes account, window, and transition key.

This keeps deduplication durable across workers while allowing two observed resets with the same upstream deadline. Using `attempted_at` was rejected because competing workers would generate different values. Reusing a synthetic value in `reset_at` was rejected because it would corrupt dashboard-visible upstream metadata.

### Confirm reset from quota movement, not deadline direction

Candidate selection continues to require an exhausted prior sample and a chronologically newer available sample that satisfies the configured availability threshold. It no longer compares the direction of `reset_at`. Both samples still require reset metadata so attempt status remains meaningful and stale available rows cannot masquerade as new transitions.

### Backfill legacy attempts without replay

The migration backfills each existing row with `legacy-reset:<reset_at>`, replaces the old uniqueness constraint, and makes `transition_key` non-null. Existing rows remain distinct and visible. A downgrade removes later duplicates per account/window/reset before restoring the old constraint, because the old schema cannot represent multiple transitions sharing a deadline.

## Risks / Trade-offs

- [A bad upstream sample can look like a reset] → Keep the exhausted threshold, available threshold, current-refresh gating, cooldown, account-state checks, and one-attempt-per-transition constraint.
- [Usage row identity is database-specific] → Build the key only from the persisted `UsageHistory.id`, which is stable and shared by all workers after refresh commit.
- [Rollback cannot represent same-deadline attempts] → Retain the earliest row for each old uniqueness tuple during downgrade and document this lossy rollback behavior in the migration.
