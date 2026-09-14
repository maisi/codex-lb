## Context

See `proposal.md` for motivation and `specs/responses-api-compat/spec.md` for the behavioral contract. The existing HTTP bridge already has exact-id denial publication, compare-and-clear retirement, bounded cleanup retry, request pinning, and a final send fence. The prompt-cache recovery shortcut enters fresh-body preparation before calling that machinery and returns immediately when the retry send succeeds, so both mutation and control flow can bypass retirement.

The fix must remain within the deployed baseline's existing lifecycle mechanisms. Tests must be synthetic, hermetic, and exercise the real denial processor plus the real next-submit path while mocking only persistence, admission, and transport boundaries.

## Goals / Non-Goals

**Goals:**

- Make the denied id observable to the existing retirement machinery before any helper clears its provenance.
- Preserve the existing proof gate and untouched full-resend body for the one bounded replay.
- Demonstrate that both retry return values prevent next-submit reuse.
- Demonstrate compare-and-clear preservation and the existing final-send race fence.

**Non-Goals:**

- Change retry selection, account routing, file pinning, downstream errors, settings, or persistence schemas.
- Treat a replay send as an upstream completion.
- Modify direct-client WebSocket recovery or import unrelated upstream fixes.

## Decisions

### Retire before fresh-body preparation

Capture the exact denied id from the request state and invoke the existing guarded retirement path before the fresh-body helper mutates `previous_response_id`, proxy-injected provenance, and replay metadata. This also places retirement before the retry-success early return. Reconstructing provenance after mutation was rejected because it would duplicate state and could misclassify client-supplied or delta-only anchors.

### Reuse existing compare-and-clear and fence mechanisms

Do not directly clear session fields in the prompt-cache branch. The shared retirement routine owns lifecycle serialization, durable owner fencing, alias selectivity, in-memory cleanup, and bounded retry behavior. This preserves a newer sibling completion and makes prepared dispatches observe the same denial generation as every other bridge path.

### Test at the denial-to-next-submit product path

Adapt the offline reproduction into the existing HTTP bridge unit suite. Parameterize retry success/failure and feature enabled/disabled. Assert the exact full replay body, next wire frame, and retained state. Add preservation and controlled concurrency assertions around the real retirement/dispatch mechanisms rather than testing a new helper in isolation.

## Risks / Trade-offs

- [Retirement bookkeeping can suspend before replay] → This ordering is intentional: publishing the fence must linearize before another prepared dispatch, and existing retirement code contains bounded/error-isolated cleanup.
- [A sibling advances during denial handling] → Existing compare-and-clear semantics retain the newer anchor while still fencing the denied id.
- [Regression fixtures accidentally omit production provenance] → Drive injection through the real prompt-cache preparation and request preparation paths, then assert full-resend provenance before denial.
- [Hermetic mocks overstate end-to-end coverage] → Keep the real denial processor and next-submit dispatch; document that no provider, reconnect implementation, or live database is exercised.

## Migration Plan

No migration or rollout setting is required. Deploy the focused code and test change with the existing prompt-cache option unchanged and default off. Rollback is the code revert; no persisted data shape changes.
