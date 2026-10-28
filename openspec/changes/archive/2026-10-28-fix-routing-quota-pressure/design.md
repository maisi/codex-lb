## Context

See proposal.md for the failure. AccountState already carries normalized quota
and a draw-weight multiplier, but account_state.py replaces its usage fields
with capped usage-plus-load values. Both tier selection and routing traces then
consume the same polluted fields. Raw token counts have no conversion to the
subscription-credit unit used by that calculation.

## Goals / Non-Goals

Keep quota thresholds and routing diagnostics stable while preserving load
sensitivity of capacity-weighted and relative-availability draws. Preserve
lease ownership, release, concurrency caps, upstream error evidence, and
additional-quota normalization. No new configuration, storage, or API fields.

## Decisions

- Keep AccountState.used_percent and secondary_used_percent as normalized
  upstream observations. Existing explicit-exhaustion priority evidence stays
  intact. Both traces and threshold checks already read these canonical fields.
- Compose load with the existing error-rate multiplier by dividing it by
  `1 + inflight_count * inflight_penalty_pct / 100 + leased_tokens / 1000000 *
  lease_token_weight`. Million-token normalization is an explicitly defined
  heuristic unit, not an estimated conversion to subscription credits. It
  keeps the configured weight dimensionless and default pressure modest.
- Reuse existing weighted-selector support for selection_weight_multiplier;
  latency weighting continues to compose with it downstream. Deterministic
  strategies retain quota/cap behavior and do not acquire new random behavior.
- Correct existing quota-help copy to describe weighting and actual quota
  thresholds. Do not change table layout or the existing used-percent API.

Alternatives rejected: hiding pressure only in the UI leaves incorrect tier
fallback; adding raw/effective quota API fields preserves the dimensional bug
and duplicates quota data; removing pressure altogether discards useful load
balancing. There is no canonical token-to-subscription-credit exchange rate.

## Risks / Trade-offs

- Busy first-tier accounts can continue serving instead of spilling on a
  synthetic quota breach. Existing concurrency caps still enforce admission,
  and weighted draws within an eligible policy pool still prefer less load.
- Custom token-weight values tuned to the broken token/credit calculation have
  a different magnitude. No safe automatic rescaling exists across plans;
  context documents define the corrected unit and rollout behavior.

## Migration Plan

Deploy the application update normally. Runtime state is replica-local and
rebuilt per selection; no data backfill or database migration is needed.
