# Context

## Failure mode

`select_account` narrows the eligible pool to the key's best rank before the
`burn_first` / `normal` / `preserve` partition. The proxy wraps it in
`_select_account_preferring_budget_safe`, which predates the priority feature
and calls `select_account` several times on subsets:

1. a recovery-probe pass over the whole pool,
2. a pass over `burn_first` accounts only, returned as soon as it selects,
3. a pass over non-`preserve` accounts below the budget threshold,
4. fallbacks over the whole pool.

The priority feature only threaded `account_priority` into each of these calls.
Inside pass 2 the pool is already `burn_first`-only, so a key ranking
`acct1 (normal)` above `acct2 (burn_first)` was served by `acct2`.

## Decisions

- **Rank first, then policy and budget inside the rank.** This is the order the
  original change already specified; the fix makes the proxy path follow it.
- **Budget threshold is the failover trigger (option B).** If the top-ranked
  account is above the sticky primary threshold (default 95 % of the 5-hour
  window) the next rank serves, so the switch happens before the first 429. The
  alternative (threshold only orders within a rank, so the top account drains
  to the hard limit) was rejected by the operator.
- **Rank order returns once every rank is over the threshold.** Nothing below
  the threshold can serve, so the strict waterfall applies again.

## Example

Key order `acct1, acct2`; both eligible.

| Case | Before | After |
|---|---|---|
| `acct2` is `burn_first` | `acct2` | `acct1` |
| `acct1` is `preserve` | `acct2` | `acct1` |
| `acct1` at 96 % of the 5-hour window | `acct2` | `acct2` |
| `acct1` at 96 %, `acct2` is `preserve` | `acct1` | `acct2` |
| both above the threshold | `acct2` if `burn_first` | `acct1` |
| `acct1` in cooldown | `acct2` | `acct2` |
