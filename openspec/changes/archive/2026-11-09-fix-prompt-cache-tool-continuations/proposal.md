## Why

Proxy-built prompt-cache continuations can attach a response with unresolved tool calls or replay response-owned tool items. Upstream rejects these with `missing_tool_output`, and retaining the rejected anchor causes repeated client failures on the same continuation.

## What Changes

- Skip prompt-cache continuation when the anchor has pending tool calls or the proposed suffix contains tool items; preserve the client's full request.
- Retire proxy-injected full-resend anchors on missing-tool-output rejection, including when transparent recovery is unavailable.
- Reuse the verified full-resend fallback once for eligible prompt-cache continuations before producing a downstream failure, preserving account ownership and pending-request guards.
- Cover completion-to-submit tool shapes, transparent recovery, client anchors, retirement across retries, and bounded recovery through bridge regression tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: Guard prompt-cache delta construction and recover safely from upstream missing-tool-output rejections without reusing the denied anchor.

## Impact

HTTP bridge request submission and upstream terminal handling, continuation outcome reasons, tests, and OpenSpec context. No settings, schema, dependency, deployment, or dashboard changes.
