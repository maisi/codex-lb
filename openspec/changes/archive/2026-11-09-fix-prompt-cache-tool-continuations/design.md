## Context

The stored count/fingerprint describes a completed request's input, whereas its response id also owns the generated output. Prefix equality proves neither that replayed tool items are new nor that the next request settles every call in the response. Session interrupted-output injection runs before request preparation and requires an already attached anchor; prompt-cache anchor injection happens later during submit, bypassing that protection.

For example, request input `[user(A)]` produces response `R` containing `function_call(C)`. The next full input `[user(A), user(B)]` previously became `previous_response_id=R, input=[user(B)]`. Upstream inherits unanswered `C` and rejects the delta. A full client transcript containing `function_call(C)` can also replay a response-owned call after the stored input boundary. Production logs establish the fallback/retirement gap, but contain no raw payloads to distinguish which tool shape caused each incident.

## Goals / Non-Goals

Preserve verified replay, account ownership, terminal settlement, and the existing downstream failure envelope. Do not reconstruct or deduplicate response output from an input-only fingerprint, change client-supplied anchor semantics, add durable fields, or change deployment state.

## Decisions

- Conservatively skip anchor injection when pending tool calls exist or the suffix contains client-executed tool protocol items. Full resend preserves client intent without inventing results or guessing output boundaries. Retaining optimization for those shapes would require stronger response-output evidence.
- Extend existing denied-anchor retirement to missing-tool-output terminals, independently of fallback eligibility, including grouped settlement. Reuse the current owner/version fences and bounded cleanup rather than create another invalidation mechanism.
- Attempt prompt-cache full resend before corruption rewriting. Rewriting first would log a client failure and set reconnect/error status even when recovery succeeds. Fresh-body installation clears the proxy-injected anchor and consumes retry-safety provenance, bounding this fallback to one attempt.
- Correlate an anonymous rejection of the unanchored resend only when it is the sole pending request and records a successful prompt-cache anchor injection. The ordinary missing-output matcher searches anchored follow-ups, so without this narrow correlation a second rejection would leave the replay pending rather than settling it.
- Keep the file-pinned branch on verified same-account replay; otherwise retain the existing account-neutral preparation proof. Record `missing_tool_output` fallback and `tool_boundary` skip reasons.

## Risks / Trade-offs

- Tool-bearing conversations lose this optional delta optimization and send their full history. Correctness takes priority; ordinary message suffixes retain continuation.
- Durable cleanup can be fenced or fail. Existing immediate local invalidation, denial ledger, and bounded retry preserve the current cleanup guarantees.
- Mock upstream tests can verify wire payloads and lifecycle behavior, but cannot establish the exact production payload or exercise a live provider. No running service is accessed.
