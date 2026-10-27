## Why

Operators cannot tell why a request was served by a given account. Request logs
record the account and the affinity key, but not the candidates, their key
priority rank, routing policy, usage against the budget threshold, or the
reason an account was skipped. Diagnosing "the key's order was ignored" meant
replaying selection by hand against a guess of the live state; the logs could
not separate continuity, the budget threshold, caps, health, model support or a
real bug.

## What Changes

- Every proxy account selection records a routing trace: the outcome (kept the
  conversation's account, moved off it, new selection, required account, no
  account), the API key priority rank that served it, the selector pass that
  decided, the sticky owner flags, and each candidate with rank, routing
  policy, status, health, 5h/7d usage, budget-threshold breach and the reason it
  could not serve. Ranked accounts that were never offered are listed apart.
- Traces are kept in a bounded per-process memory store (most recent 2,000
  requests, up to 10 selections each) and logged once per selection; account
  ids in the log follow the privacy redaction policy. Nothing is persisted.
- `GET /api/request-logs/{request_id}/routing` returns the traces, gated by
  `accounts:write` like account identity in the request list.
- The dashboard request details dialog shows a "Routing decision" panel.

## Capabilities

### Modified Capabilities

- `proxy-runtime-observability`: account selection decisions are explainable
  per request.

## Impact

- No schema change, no migration, no new setting; tracing is always on and
  cannot change which account is chosen. A failure while building a trace is
  logged and ignored.
- Dashboard-visible change in the request details dialog.
