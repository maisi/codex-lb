## ADDED Requirements

### Requirement: Prompt-cache continuations exclude unproven tool boundaries

When building an optional prompt-cache continuation from a full-history request, the proxy MUST preserve the full request without injecting `previous_response_id` if the selected completed response has pending tool calls or the proposed input suffix contains client-executed tool-call or tool-output protocol items (function, custom, apply-patch, or tool-search). An exact match of the prior request's input prefix alone MUST NOT authorize continuation across these shapes. Skips MUST record a bounded continuation reason.

#### Scenario: A completed response has an unanswered tool call

- **GIVEN** a prompt-cache bridge response completed with a client-executed tool call
- **WHEN** the next full-history request matches the completed request's input prefix
- **THEN** the proxy forwards the full request without an injected anchor
- **AND** it does not create a delta that inherits the unanswered call

#### Scenario: The suffix replays response-owned tools

- **GIVEN** a full-history request matches the stored input prefix
- **WHEN** its suffix contains a function, custom, apply-patch, or tool-search call or output
- **THEN** the proxy preserves the full request without injecting an anchor, including when the local pending-call manifest is empty

#### Scenario: A message-only continuation remains eligible

- **GIVEN** the completed response has no pending tool calls
- **WHEN** an otherwise eligible full-history request has an exact stored prefix and a message-only suffix
- **THEN** the proxy may send the suffix with its injected previous-response anchor

### Requirement: Missing-tool-output rejection retires proxy anchors and permits one verified prompt-cache resend

When upstream rejects a proxy-injected full-resend anchor with a missing-tool-output continuity error, the HTTP bridge MUST retire the rejected anchor using the same durable owner, response-id, alias, and prepared-request fences as explicit previous-response denials. Retirement MUST occur before replacing anchor provenance with a fresh body and MUST also occur when transparent replay is unavailable, fails, or several requests are settled together. A later client retry MUST NOT rebuild a continuation on that retired anchor.

For a proxy-built prompt-cache continuation with a retained retry-safe full body and no other pending requests, the bridge MUST attempt the existing verified full-body resend once before exposing the rejection downstream. The resend MUST omit the rejected anchor, preserve file-required account ownership, and permit account switching only under the existing account-neutral replay proof. Successful recovery MUST deliver the replacement response without a synthetic continuity failure or reconnect request caused by the rejected attempt. The continuation fallback outcome MUST distinguish missing-tool-output rejection from an invalid or expired response.

Client-supplied anchors MUST retain the sanitized HTTP 502 `stream_incomplete` fail-closed behavior without transparent resend or retirement on the client's behalf. Unsafe replay and concurrent pending requests MUST prevent transparent resend. A second missing-tool-output rejection of the full resend MUST terminate through normal error handling without repeating the continuation fallback.

#### Scenario: A proxy-built continuation recovers transparently

- **WHEN** upstream rejects an eligible proxy-built prompt-cache continuation with missing tool output
- **THEN** the bridge retires its anchor and sends the verified full body once
- **AND** a successful replacement response reaches the client without a continuity failure

#### Scenario: A client-supplied anchor fails closed

- **WHEN** upstream rejects a client-supplied anchor with missing tool output
- **THEN** the bridge returns sanitized `stream_incomplete` with HTTP 502
- **AND** it neither resends the request nor retires the client's anchor

#### Scenario: The next request does not reuse the rejected anchor

- **GIVEN** the bridge retired a proxy-built prompt-cache anchor after missing-tool-output rejection
- **WHEN** the client sends another request before a replacement completion, including after a failed fallback send
- **THEN** the request is sent without that anchor or its stored prefix trim

#### Scenario: File ownership survives fallback

- **WHEN** an eligible continuation containing an account-scoped file is rejected
- **THEN** the full resend retains the required account and cannot switch file ownership

#### Scenario: Unsafe or concurrent requests retire without replay

- **WHEN** a proxy-injected full-resend anchor is rejected with missing tool output and replay is unsafe or another request is pending
- **THEN** the anchor is retired and the rejection fails closed without a transparent resend

#### Scenario: Rejection of the full resend cannot loop

- **GIVEN** one full-body continuation fallback has already been sent
- **WHEN** upstream rejects that unanchored resend with missing tool output
- **THEN** the rejection terminates without another continuation fallback

## MODIFIED Requirements

### Requirement: Explicit upstream previous-response denials retire proxy-injected anchors

When upstream answers an HTTP bridge request with a `previous_response_not_found` terminal frame or a missing-tool-output continuity error, and the `previous_response_id` on that request was injected by the proxy onto a full-resend-shaped payload, the proxy MUST retire that anchor on the first denial rather than waiting for the eventless-failure poison threshold. Retirement MUST clear the durable anchor only when the denied id is still the durable latest response and the session owner fence still matches; the write MUST clear the four anchor-bound fields and delete only the matching response-id alias, preserving turn-state and sibling response aliases. The proxy MUST clear the in-memory session carrier even if durable cleanup or alias unregistering fails.

Before awaiting durable cleanup, the proxy MUST publish the denied id to the live session. Publication MUST be serialized with the submitter's final tombstone check and upstream send so either an already-started send finishes first or publication wins and fences that send. Immediately before dispatch, any already-prepared request carrying that id as a proxy-injected anchor MUST fail closed without sending another upstream frame. This revalidation MUST close the retirement/dispatch race; it MUST NOT reject a client-supplied anchor merely because the same id is tombstoned for proxy injection.

The proxy MUST also retain the denied-id generation in a bounded process-local ledger independent of the canonical live-session registry. A request that captured the durable anchor before a live session existed MUST fail closed when that generation advances during owner lookup or successor session creation. Active requests MUST pin their ledger entries until finalization so pruning cannot remove a fence that is still needed.

When a request captures a proxy-injected anchor after this process has already recorded a denial for that id, the request MUST retain that denial observation and fail closed before dispatch even when the captured generation equals the current denial generation. Owner-forward recovery that injects a durable anchor MUST perform the same capture and denial observation; it MUST NOT rely on provenance copied from an initially unanchored request.

The proxy MUST NOT retire the anchor when:

- the anchor was supplied by the client, because removing it changes the meaning of the client's own request;
- the anchor was injected onto a payload that is not full-resend shaped, because a delta-only request has no other way to convey prior context once its anchor is gone;
- the session's current anchor is no longer the denied id, because a concurrent request may have completed and advanced it.

When a durable clear raises, the proxy MUST NOT report the anchor as retired, MUST still clear the in-memory anchor, and MUST retain the bounded cleanup retry so a transient failure is not lost. When the durable clear returns no matching row, the proxy MUST treat that no-match as a terminal fenced outcome for this cleanup attempt and MUST NOT spend the retry budget on it; it MUST preserve the local alias and denial fence because the durable owner or latest anchor may have advanced. A durable record that still carries the denied id can then be retired by the matching owner rather than by a stale epoch.

Retirement is bookkeeping and MUST NOT change how the denial is delivered downstream. A failure while retiring MUST NOT propagate into terminal-event handling.

A denial that settles several requests sharing one anchor MUST retire that anchor once, on the same terms.

Unless an eligible proxy-built prompt-cache continuation recovers through a verified full-body resend, the denial MUST be reported to the client as `stream_incomplete`, so the client retains its own anchor and is not driven into a full-history resend. Client-supplied anchors MUST always retain this fail-closed behavior.

#### Scenario: A denied proxy-injected anchor is retired immediately

- **GIVEN** an HTTP bridge session whose stored anchor was injected by the proxy
- **WHEN** upstream answers the anchored request with `previous_response_not_found`
- **THEN** the proxy clears the durable continuity record under the session's owner epoch
- **AND** clears the in-memory session anchor and its stored input count and prefix fingerprint
- **AND** the next turn on that session dispatches without a `previous_response_id`

#### Scenario: The following turn is not trimmed against a denied anchor

- **GIVEN** a proxy-injected anchor was denied by upstream on the previous turn
- **WHEN** the client sends a full resend of the conversation on the next turn
- **THEN** the request MUST NOT be trimmed against the denied anchor's stored prefix
- **AND** upstream receives the resent conversation rather than a suffix of it

#### Scenario: A concurrent completion protects the current anchor

- **GIVEN** a proxy-injected anchor is denied by upstream
- **AND** another request on the same session completed first and advanced the session anchor to a different response id
- **WHEN** the denial is handled
- **THEN** the proxy MUST NOT clear the session anchor
- **AND** it MUST still tombstone the denied id so an already-prepared proxy-injected request cannot dispatch it

#### Scenario: Client-supplied anchors are left alone

- **GIVEN** an HTTP bridge request carries a `previous_response_id` the client supplied
- **WHEN** upstream answers it with `previous_response_not_found`
- **THEN** the proxy MUST NOT retire the anchor on the client's behalf

#### Scenario: A delta-only payload keeps its injected anchor

- **GIVEN** the proxy injected an anchor onto a payload that is not full-resend shaped
- **WHEN** upstream answers that request with `previous_response_not_found`
- **THEN** the proxy MUST NOT clear the anchor
- **AND** the request keeps the only reference it has to its prior context

#### Scenario: A fan-out denial retires the shared anchor once

- **GIVEN** several pending requests on one session share a proxy-injected anchor
- **WHEN** upstream answers with a single `previous_response_not_found` that settles all of them together
- **THEN** the proxy retires that anchor before the grouped settlement completes

#### Scenario: A prepared denied anchor is rejected before dispatch

- **GIVEN** a request was prepared with a proxy-injected anchor
- **AND** another request receives `previous_response_not_found` for that anchor before the prepared request reaches the upstream send
- **WHEN** the prepared request reaches its final dispatch check
- **THEN** the proxy fails it closed as `stream_incomplete`
- **AND** the proxy MUST NOT send that denied anchor upstream again

#### Scenario: Denial publication wins against a prepared dispatch

- **GIVEN** a request is prepared with a proxy-injected anchor while another request receives `previous_response_not_found` for that anchor
- **WHEN** denial publication acquires session lifecycle ownership before the prepared request's final send section
- **THEN** the denied id is tombstoned before the prepared request revalidates
- **AND** the prepared request fails closed without sending an upstream frame

#### Scenario: A detached predecessor fences an absent-session capture

- **GIVEN** a request captures a proxy-injected durable anchor before a canonical live session exists
- **AND** a detached predecessor receives `previous_response_not_found` for that anchor while the request is resolving ownership
- **WHEN** successor session creation completes and the request reaches final dispatch
- **THEN** the process-local denial generation MUST fail the request closed as `stream_incomplete`
- **AND** the successor MUST NOT send the denied anchor upstream

#### Scenario: A stale durable recapture remains fenced after cleanup failure

- **GIVEN** a detached predecessor records a denial for a proxy-injected anchor
- **AND** durable anchor cleanup fails, leaving the durable row unchanged
- **WHEN** a later request captures that same durable anchor after the denial was recorded
- **THEN** the request MUST retain the existing denial observation
- **AND** it MUST fail closed as `stream_incomplete` before dispatch

#### Scenario: Owner-forward recovery observes an existing denial

- **GIVEN** owner-forward recovery injects a durable proxy anchor into a successor request
- **AND** this process has already recorded a denial for that anchor
- **WHEN** the recovery retry request state is prepared
- **THEN** the retry MUST retain the denial observation
- **AND** it MUST fail closed before sending the denied anchor upstream

#### Scenario: Sibling response aliases survive retirement

- **GIVEN** a session has a denied response alias and another valid response alias
- **WHEN** the denied anchor is retired
- **THEN** only the denied response alias is removed
- **AND** the valid response alias and turn-state aliases remain routable

#### Scenario: An unconfirmed durable clear still drops the in-memory anchor

- **GIVEN** a denied proxy-injected anchor whose durable clear is fenced or fails
- **WHEN** the denial is handled
- **THEN** the proxy MUST clear the in-memory session anchor
- **AND** MUST NOT report the anchor as retired

If alias unregistering raises after the durable clear, the same in-memory cleanup MUST still occur.

The process-local denial fence MUST retain its positive generation while any
request still pins the denied id, even after durable cleanup succeeds. Such a
prepared request MUST remain fenced until its final pin is released; the fence
may then be removed. Fence state MUST be bounded to one current denial slot per
active durable or local owner plus active request pins, and a session close or
durable-owner epoch change MUST retire the old owner's unpinned slot without
clearing a successor epoch's slot. A close MAY retain an otherwise unpinned
durable denial slot while that session still records an unresolved durable
cleanup, so a stale row cannot be recaptured; the slot MUST be retired when
cleanup succeeds or the durable row is confirmed absent.

When several late predecessor denials arrive for one durable owner, only the
newest unpinned predecessor slot MUST be retained while its durable cleanup is
unresolved. Older predecessor slots MUST remain fenced while request pins are
active, then MUST be retired when those pins release or when a newer owner
confirms durable cleanup. This keeps predecessor churn bounded without
allowing an already-prepared request to redispatch a denied anchor.

#### Scenario: Late predecessor churn remains bounded

- **GIVEN** one durable owner advances through more than the process-local
  denial-ledger bound
- **AND** each successor denial is followed by a late predecessor denial
- **WHEN** no predecessor request retains an active ledger pin
- **THEN** the ledger retains the current denial and at most the newest
  unresolved predecessor denial for that owner
- **AND** a current-owner durable clear retires the unresolved predecessor
  slot

#### Scenario: Pinned predecessor survives bounded churn until release

- **GIVEN** a late predecessor denial still has an active prepared-request pin
- **WHEN** a newer predecessor denial is recorded for the same durable owner
- **THEN** the pinned predecessor remains fenced until its request finalizes
- **AND** releasing the final pin removes that superseded predecessor slot

#### Scenario: A retirement failure cannot change the denial delivered downstream

- **GIVEN** the bookkeeping performed while retiring a denied anchor raises
- **WHEN** the denial is handled
- **THEN** the error MUST NOT propagate into terminal-event handling

#### Scenario: Durable cleanup preserves a prepared request's denial fence

- **GIVEN** a request has pinned a proxy-injected anchor while another request receives `previous_response_not_found`
- **WHEN** the durable clear succeeds
- **THEN** the denied fence keeps its positive generation until the prepared request releases its pin
- **AND** the prepared request remains fenced during that interval
- **AND** the fence is removed after the final pin is released

#### Scenario: A successor epoch survives predecessor fence cleanup

- **GIVEN** a successor owns the same durable session id at a newer epoch
- **WHEN** the predecessor closes or its durable clear completes
- **THEN** cleanup removes only the predecessor's unpinned fence state
- **AND** the successor's current denial slot remains active
