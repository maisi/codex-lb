## Context

The Accounts page already exposes `Force probe`, which is a recovery action that refreshes account usage and health eligibility. Proxy warmup is a separate compact request path that exercises token acquisition and upstream model transport, but the existing forced warmup API targets every eligible account in an API key's pool rather than one dashboard-selected account.

This change crosses the accounts dashboard API, proxy warmup service, frontend account actions, and request logging. It must preserve dashboard authorization, account ownership, borrowed-account token vending, and the warmup path's intentional exclusion from usage accounting.

## Goals / Non-Goals

**Goals:**

- Force the compact proxy warmup request through exactly one selected active account.
- Record the attempt as warmup traffic with the existing structured result fields.
- Present an immediate `Warm now` account action with clear pending and outcome feedback.
- Reuse existing proxy warmup behavior rather than create another upstream request implementation.

**Non-Goals:**

- Replace, rename, or alter `Force probe`.
- Warm all accounts associated with an API key.
- Change scheduled warmup selection, quotas, usage accounting, or account health policy.
- Add persisted configuration or a new setting.

## Decisions

### Add a dashboard account action endpoint

Add `POST /api/accounts/{account_id}/warmup` under the existing accounts dashboard API. The route uses the standard dashboard write dependency, resolves the selected account, rejects non-active accounts, and delegates the actual request to the proxy warmup service.

An account endpoint is preferred over extending `/v1/warmup/force` because dashboard account selection does not have an API-key pool context and must never broaden to another account.

### Extend the compact warmup path with explicit account targeting

Expose a service entry point that accepts one resolved account and executes the existing compact warmup request machinery. Targeting bypasses usage-based eligibility because the operator explicitly selected the account, but it does not bypass active status, credential acquisition, ownership, or transport handling.

Reusing the warmup machinery preserves model selection, compact request shape, live token vending for borrowed accounts, request-log classification, settlement exclusions, and structured failures. Calling Force probe first was rejected because it still would not exercise the upstream model window and would conflate two operator intents.

### Return one structured warmup result

The endpoint returns the existing warmup result shape for the selected account rather than an aggregate pool response. Expected upstream or credential failures are represented in that result so the dashboard can show the useful failure reason; authorization, missing-account, and inactive-account errors remain HTTP errors.

### Make the frontend action immediate and distinct

Add `Warm now` beside the existing account actions without a confirmation dialog. Disable it for inactive accounts, read-only users, or while its mutation is pending. Show the structured warmup message on success or failure and invalidate account/request-log queries after settlement.

## Risks / Trade-offs

- [Operators can repeatedly create upstream warmup traffic] -> Preserve pending-state suppression and use the existing compact request rather than a full completion.
- [A future refactor could silently turn targeting back into pool selection] -> Add route-level tests asserting that only the selected account reaches the warmup executor.
- [Borrowed accounts may not have stored credentials] -> Preserve live token vending instead of requiring local refresh credentials.
- [Expected upstream failure returned as HTTP success can be misread] -> Treat the structured result's success field as the frontend mutation outcome and display its message.

## Migration Plan

Deploy the additive endpoint and frontend action together. No database migration or compatibility shim is required. Rollback removes the endpoint and action while leaving existing warmup and Force probe behavior unchanged.

## Open Questions

None.
