## Why

The per-API-key account priority change decided that a key's explicit account
order outranks account-level `routing_policy` (`burn_first` / `preserve`).
`select_account` implements that, but the proxy never calls it on the whole
pool for a fresh pick. Both the sticky and the unbound selection paths go
through `_select_account_preferring_budget_safe`, which first runs a
burn-first-only pass and then drops `preserve` and over-budget accounts before
`select_account` narrows by rank. Rank can then only order what those filters
kept, so in production:

- a lower-ranked `burn_first` account beats a better-ranked `normal` one, and
- a lower-ranked `normal` account beats a better-ranked `preserve` one.

The existing unit tests call `select_account` directly and pass anyway.

## What Changes

- The budget-safe selector settles the serving rank over the whole pool before
  its burn-first and budget passes, then runs those passes inside that rank
  only. Routing policy still orders accounts that share one rank (today: the
  unranked tail).
- The sticky reallocation budget threshold stays the failover trigger: the
  serving rank comes from the accounts below the threshold while any of them
  can serve, and from the whole pool once none can.
- Recovery admission, continuity owners, and keys without ranks keep their
  current behavior.

## Capabilities

### Modified Capabilities

- `account-routing`: per-key account priority holds on the proxy selection
  path, not only inside `select_account`.

## Impact

- Affects fresh account selection for API keys with assigned accounts, on the
  sticky and unbound paths and for the burn-first reallocation target.
- No schema, migration, API, setting, or dashboard change.
