## Why

OpenClaw resends complete Responses histories without a hard session identifier, so codex-lb preserves account locality but cannot safely continue from the prior upstream response. Operators also cannot quantify provider-reported prompt-cache reuse by API key over time.

## What Changes

- Add a per-API-key prompt-cache continuation opt-in that defaults to false and is exposed through API-key persistence, CRUD APIs, and dashboard create/edit controls.
- For opted-in prompt-cache-affinity Responses requests, inject `previous_response_id` and forward only new input items when exact stored-prefix, API-key, model, account, ownership, and serialization checks prove continuation.
- Fall back to the original full resend on mismatch, compaction/rewrite, stale response, concurrency, ownership conflict, or any ambiguity; classify only proven continuation as `follow_up`.
- Add explicit bounded continuation outcome observability without claiming token savings that cannot be measured reliably.
- Extend Reports with API-key filtering/grouping and accurate total input, cached input, cache-hit ratio, and daily trends from request-log usage.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `api-keys`: persist and expose the default-off continuation policy per API key.
- `responses-api-compat`: safely promote an opted-in prompt-cache-affinity full resend to verified continuation.
- `sticky-session-operations`: preserve soft affinity while requiring hard owner proof for each promoted continuation turn.
- `proxy-runtime-observability`: expose continuation outcomes and API-key-scoped cache usage metrics.
- `frontend-architecture`: expose API-key policy controls and cache metrics in the dashboard.

## Impact

- **Database/API**: API-key boolean migration and CRUD contract; Reports query/response extensions.
- **Proxy**: HTTP Responses bridge continuation preparation, fallback, routing-stage, and counters.
- **Dashboard**: API-key create/edit controls plus Reports filters, grouping, summary, and trends.
- **Tests**: migration/API persistence, continuation safety/fallback, report aggregation/filtering, and frontend rendering.
