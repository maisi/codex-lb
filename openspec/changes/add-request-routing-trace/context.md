# Context

## Why notes instead of a result object

Account selection spans the sticky path, the unbound path, tier narrowing and
the budget-safe passes, with retries and recursion. Threading an explanation
object through every branch would touch dozens of signatures. Instead
`LoadBalancer.select_account` opens a draft in a ContextVar, and a handful of
places leave notes: the candidate pool (before and after cap / hard-sticky
narrowing), the sticky owner decision, and the serving rank plus deciding pass
of the budget-safe selector. Outside a capture every note is a no-op.

Per-candidate eligibility is computed afterwards from copies of the states the
decision used, with the same `select_account` hard filters (single-account
strategy), so the explanation cannot drift from the selector's rules. Copies
matter because selection resets elapsed rate limits on the live objects.

## Why in memory

Persisting traces would add a request-log column, which on Oracle is the first
change after the frozen baseline. Traces are a diagnostic for recent behaviour,
so a bounded per-process store plus one log line per selection covers the use
case without schema risk. The log line keeps older decisions searchable.

## Example

Key tiers `[[acct1 burn_first, acct2 normal], [acct3 burn_first]]`, acct1
rate-limited, acct2 at 97 % of its 5-hour window:

- outcome `new_selection`, selected acct3, serving rank 1 (shown as 2);
- decided by `burn_first`;
- acct1 `rate_limited`, acct2 eligible but over the budget threshold.

That reads as "acct2 crossed the threshold, so the next rank served", which is
the documented threshold behaviour rather than a priority bug.
