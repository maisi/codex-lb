# Add per-API-key account priority

## Why

An API key can already be *scoped* to a set of accounts through
`api_key_accounts` plus `account_assignment_scope_enabled`, but that set has no
order: the selection path filters with `account.id in assigned_ids`, so the
balancer's usual least-used-first ranking decides which assigned account serves
the request.

Operators need the opposite for some keys: spend one account's quota first and
only move on when it can no longer serve. Today the only ordering controls are
account-level (`routing_policy` = `burn_first` / `preserve`), which are global —
they cannot express "key A prefers account 1, key B prefers account 2".

## What Changes

- `api_key_accounts` gains a `priority` column (lower wins). Assignment order
  supplied through the API is persisted as that rank, and the ORM relationship
  loads most-preferred first, so readers get the selection order without
  re-sorting.
- `select_account` accepts an `account_priority` mapping and narrows the
  eligible pool to its best still-eligible rank before applying routing-policy
  preference. Failover needs no new logic: an account that is rate-limited,
  quota-exhausted, paused, or in error backoff has already left the pool.
- Priority is an ordering concern, not a restriction. Unranked accounts rank
  after every ranked one, so a key may still reach an account it does not rank —
  as a last resort. Hard restriction remains `account_assignment_scope_enabled`,
  which becomes explicitly settable through the API instead of being derived
  only from "has assignments".

## Decisions

- **Strict waterfall, not a tie-break.** Rank dominates usage-based ordering, so
  a preferred account is drained before the next one is touched. This is the
  point of the feature; the cost is that a preferred account runs hot while a
  lower-ranked one idles.
- **Priority outranks `preserve` / `burn_first`.** The pool is narrowed by rank
  *before* the routing-policy partition, so an explicit per-key order wins over
  account-level policy. Policy still orders accounts *within* one rank.
- **Priority never re-homes a pinned conversation.** It applies to fresh
  selection only. Continuity-pinned requests (`previous_response_id`, sticky
  owner resolution, grace re-pinning) keep resolving to their existing owner.
- **Recovery admission still wins.** A due PROBING recovery probe is a liveness
  admission and is chosen before rank narrowing, so priority cannot make a
  lower-ranked account's PROBING state permanent.

## Impact

- Existing keys are unaffected: with no ranks, `account_priority` is `None` and
  selection is byte-for-byte the previous behavior.
- No access widening. The scope flag keeps its derived default, so assigning
  accounts still restricts unless an operator explicitly says otherwise.
