# Context

## Model

A key's account priority is a list of tiers, most-preferred first. Accounts in
one tier share a rank. The selector already treats equal ranks as one pool
(`_best_priority_group`, and the budget-safe wrapper narrows to the serving
rank), so within a tier the account `routing_policy` and the routing strategy
decide, exactly as they do for a key without ranks.

## Decisions

- **Two request fields, not one.** `assigned_account_ids` stays valid and means
  "one account per rank", so existing API clients and automation keep working.
  `assigned_account_tiers` is the richer form. Accepting both at once would need
  a merge rule nobody asked for, so it is rejected.
- **Rank lives in the existing `priority` column.** Equal values mean "same
  tier". No schema change.
- **Legacy rows are renumbered.** Assignments created before ranking existed all
  have priority 0. The proxy used to read rank from list position, so those keys
  were a waterfall in `(priority, created_at)` order; reading the column as-is
  would silently turn each into one balanced tier. The migration gives them
  distinct ranks in `(priority, created_at, account_id)` order first.
- **Order inside a tier carries no meaning.** It is listed by
  `(created_at, account_id)` only so it is stable; the dashboard compares tiers
  ignoring that order.

## Example

Key tiers `[[team-a, team-b], [reserve]]`, `team-b` is `burn_first`:

- both team accounts eligible: `team-b` (burn_first inside the tier);
- `team-b` rate-limited: `team-a`;
- both team accounts out: `reserve`.

With `team-a` and `team-b` both `normal`, `capacity_weighted` spreads requests
between them by remaining capacity.
