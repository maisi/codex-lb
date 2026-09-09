# Recovery evidence and operational context

Issue #27 was reproduced on both public HTTP endpoints with a rate-limited owner: the full request contained a durable-prefix match, a completed custom tool call/result and a fresh goal instruction, yet returned 502 `previous_response_owner_unavailable`. The old manifest helper rejected the trailing user message.

The implementation extends that proof only after the complete batch. It validates new input using both fresh-input content checks and the canonical allowed-fields/ownership validator. It keeps the existing full-body projection, exact manifest, account scope, file pins and pre-dispatch recovery. The existing session recovery machinery retires the old anchor and records the replacement; no new owner store is introduced.

For example, owner A finishes a shell tool call, reaches its five-hour limit, and the client resends the full history with the result and a new goal instruction. The request goes to eligible B without A's response ID and later anchored turns continue on B. An A-owned file, missing tool result or unknown ownership field prevents replay; three repeated requests remain pre-dispatch and never call the retry-circuit failure writer.

Verification: before-fix public regression failed on both HTTP endpoints; 552 replay/HTTP/WebSocket tests pass; all 32 endpoint/rate-or-quota/explicit-anchor/safe-or-rejected recovery scenarios pass; 377 owner/continuity tests pass. Ruff, type checking, architecture, timing seams, cancellation safety, strict change validation and all 63 main spec validations pass. The 32-case run includes literal checks for actionable error guidance, not only a comparison against the implementation constant.

Regression scenarios were adapted from upstream PR #2121 and expanded. Its reported concern about relaxed validation of trailing input is covered by canonical ownership validation and explicit unknown-field/owner-metadata tests. Opaque compaction remains nonportable. Direct WebSocket behavior keeps its existing ownership policy and stable error code while gaining the same actionable guidance.

PR #30 follows integration PR #29. Final-head GitHub checks and clean mergeability remain deployment/merge gates; local verification does not replace them.
