## Why

A soft sticky owner (prompt-cache, sticky-thread or Codex-session affinity)
keeps its conversation as long as it is healthy and below the budget threshold,
whatever the API key's ranking or the owner's routing policy says. The
prompt-cache affinity TTL does not end that: every kept turn refreshes the
row, so an active conversation never expires.

In production on 2026-10-28 a conversation of a key ranked
`[[d717, 9d24], [eeab]]` stayed on `eeab` (rank 2, `preserve`) for hours while
both rank-1 `burn_first` accounts were free at 0 % of their 5-hour window.
New conversations went to rank 1 correctly; only the running one never came
back. `preserve` is meant as a fallback, and once a conversation has gone quiet
its upstream prompt cache is cold anyway, so keeping it there buys nothing.

## What Changes

- Before keeping a soft owner, selection asks what a new conversation would
  get (same ranking, policy and budget rules, without a recovery-probe
  admission). The owner is released and the mapping rebound when:
  - the owner's routing policy is `preserve` and that pick is a different,
    non-`preserve` account; or
  - the key ranks accounts, the conversation has been idle for at least
    10 minutes (its prompt cache is cold) and that pick holds a better rank.
- The owner lookup reports the live row's last use (`updated_at`) for
  TTL-based kinds; durable kinds report none and keep their owner as before.
- Hard continuity owners (`previous_response_id`, turn state, bridge and file
  ownership) are unchanged.
- Routing traces gain the owner flags `preserve_release` and `rank_return`;
  the dashboard names them.

## Capabilities

### Modified Capabilities

- `sticky-session-operations`: soft owners yield to `preserve` semantics and,
  once cold, to the API key's rank.

## Impact

- Proxy sticky selection, sticky owner lookup, routing trace flags, dashboard
  routing panel (en/ko/zh-CN), docs. No schema, setting or API change.
- A released conversation pays one uncached turn on its new account; the cold
  rule only fires when that turn would have been uncached anyway.
