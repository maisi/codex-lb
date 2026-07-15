## Why

Weekly limit warm-up currently requires the refreshed reset deadline to be later than the exhausted sample's deadline. Upstream can replenish a weekly limit outside its expected schedule while preserving or moving that deadline earlier, so codex-lb observes an exhausted-to-available transition but skips the warm-up.

## What Changes

- Treat an observed transition from an exhausted selected quota window to available quota as sufficient reset confirmation, regardless of how the upstream `reset_at` value moves.
- Persist a transition identity separately from the upstream reset deadline so an unplanned reset with an unchanged deadline is not mistaken for an earlier warm-up attempt.
- Preserve the existing opt-in, account-safety, availability-threshold, cooldown, and durable deduplication protections.
- Add regression coverage for unplanned weekly resets whose deadline is unchanged or earlier than the prior exhausted sample.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `usage-refresh-policy`: Expand reset-confirmed limit warm-up to recognize exhausted-to-available transitions that occur outside the expected reset schedule.
- `database-migrations`: Deduplicate warm-up attempts by observed transition while preserving the upstream reset deadline as attempt metadata.

## Impact

- Limit warm-up candidate selection in `app/modules/limit_warmup/service.py`.
- Warm-up persistence model, repository, account reconciliation, and Alembic schema.
- Unit coverage in `tests/unit/test_limit_warmup.py`.
- No external API or default-setting changes.
