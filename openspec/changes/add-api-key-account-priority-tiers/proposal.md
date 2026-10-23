## Why

Per-key account priority is a strict waterfall with one account per rank: the
order of `assigned_account_ids` is the rank. Operators also want "use these two
accounts together, and only then that one", for example to spread a team key
across two accounts and keep a third as reserve. That cannot be expressed today:
equal ranks are impossible, so every listed account but the first idles until
the ones above it fail, and account-level `burn_first` / `preserve` and the
routing strategy never matter for listed accounts.

## What Changes

- API keys accept `assigned_account_tiers` (`[["a", "b"], ["c"]]`) as an
  alternative to `assigned_account_ids`. Accounts in one tier share a rank. A
  flat `assigned_account_ids` list keeps its meaning (one account per rank);
  sending both is rejected.
- Responses carry `assigned_account_tiers` next to the flat
  `assigned_account_ids`.
- The rank is persisted in the existing `api_key_accounts.priority` column, and
  the proxy reads it from there instead of from list position. Selection already
  narrows to the best eligible rank and lets routing policy and strategy decide
  within it, so shared ranks need no selector change.
- A data migration renumbers legacy assignments that all defaulted to priority
  0, so existing keys keep their current waterfall instead of becoming one tier.
- Dashboard: the priority list in the API key dialogs can link an account to the
  rank above it and split it off again.

## Capabilities

### Modified Capabilities

- `api-keys`: the account assignment contract gains rank tiers.
- `account-routing`: accounts sharing a per-key rank are balanced.

## Impact

- No new setting; keys that never use tiers behave as before.
- One data-only Alembic revision (no schema change).
- Dashboard-visible change in the API key create and edit dialogs.
