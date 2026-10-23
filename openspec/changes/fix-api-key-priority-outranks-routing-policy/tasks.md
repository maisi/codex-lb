# Tasks

- [x] Settle the serving rank in `_select_account_preferring_budget_safe` before
      the burn-first and budget passes, and run those passes inside that rank.
- [x] Keep the budget threshold as the trigger to move down one rank, and fall
      back to rank order once every rank is over the threshold.
- [x] Fall back to the unnarrowed passes when a pool-relative gate rejects the
      narrowed rank, so the fix never fails a request the old path served.
- [x] Unit tests on the budget-safe selector across routing strategies
      (burn_first below, preserve on top, threshold failover, all over budget,
      cooldown failover, policy inside a tier, recovery carve-out, no ranks).
- [x] Sticky-path tests for a fresh thread against burn_first and preserve.
- [x] Integration test through the compact proxy route with a ranked API key.
