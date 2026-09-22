## Purpose and scope

`model-catalog-compat` describes the model metadata and account-capability
knowledge used by Codex-native and OpenAI-compatible endpoints and by request
routing. The quota-catalog incident exposed an important boundary: temporary
capacity exhaustion changes whether an account can serve now, while it does
not by itself prove that the account lost a model or service-tier entitlement.
The normative behavior is in [spec.md](spec.md).

This capability covers bootstrap and persisted catalog behavior, upstream
refresh reconciliation, per-account provenance, and the way catalog evidence
feeds continuity and model-policy checks. It does not grant quota, transfer
account-bound history, or override file, API-key, security, plan, or
service-tier restrictions.

## Decisions and rationale

The scheduler still fetches catalogs only from active accounts. Accounts in a
temporary rate-limited or quota-exhausted state are excluded from that fetch
and from request selection, but their prior account-specific catalog evidence
can remain in the registry while their plan is unchanged. Keeping these two
sets separate prevents an unavailable owner from becoming a misleading
"outside model policy" error while preserving hard continuity ownership.

The registry reuses its existing per-account snapshot and persistence model.
It carries forward an account's model and service-tier evidence only when the
stored plan matches the account's current plan. Unknown accounts remain
unknown; capability evidence is never copied from a sibling account. A fresh
authoritative omission, account removal, administrative deactivation,
authentication-required state, or plan change removes the old evidence.
This avoids a second cache and keeps replicas consistent through the existing
persisted snapshot and invalidation path.

## Constraints and failure modes

- Retention is knowledge only. Quota admission, owner pins, API-key scope,
  security routing, and service-tier selection still decide whether a request
  may run.
- If every known account is temporarily unavailable, the refresh reconciles
  the snapshot instead of clearing it. Accounts without prior provenance do
  not acquire capability membership during that pass.
- If the last advertiser is removed or a fresh authoritative catalog omits a
  model, the model is suppressed even when bootstrap or stale plan data would
  otherwise mention it.
- A plan change invalidates the old plan's evidence. A later quota reset can
  reuse retained evidence only after the account is otherwise eligible.
- A replica that loads the persisted snapshot must observe the same capability
  membership and must still reject an exhausted account at request time.

## Concrete incident flow

Suppose Plus owner A and Plus owner B previously advertised Astra. Both reach
their five-hour quota while a business account remains healthy. The next
refresh fetches the business catalog, retains the same-plan Plus evidence, and
keeps A and B out of selection. A continuation still recognizes its required
owner as an Astra-capable account, so the client receives the owner-unavailable
response rather than a model-policy conflict. After A's quota resets, normal
eligibility checks may select A without waiting for another model refresh. If
A changes plan or is removed, the old Astra evidence is discarded.

## Operational notes

Monitor the model-refresh logs for the retained-catalog count and compare
continuity errors with model-policy conflicts. When diagnosing a 502/503
owner-unavailable response, inspect account status, reset time, and owner
affinity before changing model allowlists. A catalog refresh or replica
restart should load the persisted snapshot; no new environment variable or
dashboard setting is required for this behavior.

Related contracts include [database-migrations](../database-migrations/spec.md)
for the beta9 history convergence and the proxy continuity specifications
that define when account-bound history may recover or must fail closed.
