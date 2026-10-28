# Context

## Why 10 minutes

Upstream prompt-cache prefixes typically survive 5 to 10 minutes of
inactivity. After 10 idle minutes the next turn is uncached on any account, so
returning the conversation to the key's better rank costs nothing extra. The
affinity TTL (default 1800 s) cannot serve as that signal: it is measured from
the last kept turn and refreshed by every turn, so an active conversation
never reaches it. The threshold is a constant
(`PROMPT_CACHE_COLD_AFTER_SECONDS`), not a setting; nothing in production
needed tuning yet.

`updated_at` lags the true last use by at most the refresh-skip window
(15 s), which is irrelevant against 600 s. Durable kinds without a TTL do not
rewrite `updated_at` on a kept turn, so the lookup reports no last use and
those owners count as warm.

## Why preserve releases immediately

`preserve` means "use only when nothing else can serve". A conversation that
landed on a `preserve` account during a shortage would otherwise stay there
until the conversation ends. The release costs one uncached turn; the rule
fires only when the pick a new conversation would get is a non-`preserve`
account, so a key that ranks its `preserve` account first keeps using it.

## The what-if pick

The pick runs the same budget-safe selector as a new conversation, seeded with
the sticky key. Seeding skips the recovery-probe admission, which would
otherwise re-home a conversation onto a probing account, and only the pick's
rank and policy are used. The actual new owner is chosen afterwards by the
normal reallocation path. The pick runs with routing-trace notes suspended so
the trace's serving rank and deciding pass describe the real selection.

## Production example (2026-10-28)

Key `08a03345…`, tiers `[[d717, 9d24], [eeab]]`, `d717`/`9d24` `burn_first`
at 0 % primary, `eeab` `preserve`. 23 of 25 traced selections in two hours
were `kept_owner` on `eeab` for one running conversation; the one new
conversation went to `d717`. With this change the running conversation leaves
`eeab` on its next turn (`preserve_release`).
