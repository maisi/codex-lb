## Context

Prompt-cache affinity is currently soft routing locality. HTTP bridge sessions already retain the latest response ID and an exact canonical fingerprint of the completed full input, but implicit anchor injection is restricted to hard Codex sessions. OpenClaw sends full histories on `/v1/responses`, so a narrow opt-in can reuse this metadata without changing default behavior. Request logs already persist provider-reported `input_tokens` and `cached_input_tokens`, making those fields the only defensible source for cache analytics.

## Goals / Non-Goals

**Goals:**

- Keep all existing keys and non-opted-in clients behaviorally unchanged.
- Promote a prompt-cache turn only with exact prefix and owner/account/model proof at a serialized send point.
- Preserve a retry-safe original full-resend body for invalid or expired anchors.
- Show provider-reported cache usage by API key and date range with clear subset semantics.

**Non-Goals:**

- Do not infer identity from a weak prompt-cache key alone.
- Do not estimate saved tokens, avoided cost, or avoided prefix tokens from incomplete evidence.
- Do not enable the setting for any key or deploy it.
- Do not make prompt-cache affinity globally hard.

## Decisions

### Store an explicit default-false API-key policy

The API-key row is the policy source of truth and flows through the existing authenticated `ApiKeyData`. A non-null false server default backfills existing rows and keeps zero-config behavior unchanged. Regeneration preserves the policy.

### Prove continuation from the completed full-input prefix

Continuation requires a list input longer than the stored prefix, exact canonical fingerprint equality for that prefix, the same API-key-scoped bridge lane, the same model and account owner, no explicit client anchor, and no pending/concurrent ambiguity. The wire request receives the completed response ID and only the suffix; the request state retains the full incoming count/fingerprint for the next turn.

### Linearize prompt-cache continuation with response creation

Prompt-cache continuation is prepared only while the bridge response-create gate owns the send slot. This prevents two concurrent full resends from independently selecting the same stale parent. If the invariant cannot be established at that point, the request remains a full resend and `first_turn`.

### Fall back once with the original request

When an implicitly injected response is rejected as missing or expired, retry with the untouched full-resend request and record fallback. Other proof failures skip continuation before sending. Explicit client anchors retain existing error semantics.

### Report only observed cache usage

Reports calculate total input as the sum of non-negative input tokens and cached input as each row's cached value clamped to its input value. Cache-hit ratio is `cached_input_tokens / input_tokens`, or zero when input is zero. Cached input is a subset of input and is displayed as such, never stacked on top of total input. Continuation attempts/success/skips/fallbacks use bounded runtime counters; per-key saved-token estimates are omitted because request logs do not reliably persist the exact removed prefix for every outcome.

## Risks / Trade-offs

- [Stale/expired upstream response] -> retry only proxy-injected anchors with the preserved full-resend body and record fallback.
- [Concurrent turns] -> derive the anchor only under serialized response-create ownership; otherwise skip.
- [Compaction or rewritten history] -> exact prefix mismatch leaves the request self-contained.
- [Deleted API keys] -> historical report groups retain a stable deleted-key label from the logged ID when current metadata is unavailable.
- [Provider usage gaps] -> labels state that cache metrics cover logged provider-reported usage; missing usage contributes zero tokens rather than inferred values.

## Migration Plan

1. Add the non-null default-false API-key column at the current Alembic head.
2. Deploy code with all keys disabled; no operational policy changes occur automatically.
3. A later operator action may enable only the intended OpenClaw key.
4. Downgrade removes the column and restores legacy behavior.
