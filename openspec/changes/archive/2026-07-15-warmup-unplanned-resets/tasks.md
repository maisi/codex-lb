## 1. Persistence

- [x] 1.1 Add durable warm-up transition identity to the ORM model and repository uniqueness logic.
- [x] 1.2 Add an Alembic migration that backfills legacy attempts, replaces the uniqueness constraint, and supports downgrade.
- [x] 1.3 Update account-merge reconciliation and database schema expectations for transition identity.

## 2. Warm-up Detection

- [x] 2.1 Derive reset-confirmed transition keys from persisted available usage rows.
- [x] 2.2 Accept exhausted-to-available transitions with later, unchanged, or earlier reset deadlines while retaining existing safety gates.
- [x] 2.3 Preserve one-per-cycle transition keys for staggered idle warm-up.

## 3. Verification

- [x] 3.1 Add regression tests for earlier and unchanged weekly reset deadlines, including a prior same-deadline attempt.
- [x] 3.2 Add repository and migration coverage for transition-key uniqueness and legacy backfill.
- [x] 3.3 Run targeted tests, type checks, and strict OpenSpec validation.
