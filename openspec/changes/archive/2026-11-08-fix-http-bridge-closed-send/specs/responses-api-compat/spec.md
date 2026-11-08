## ADDED Requirements

### Requirement: HTTP bridge closed-socket sends preserve dispatch safety and terminal errors

An HTTP bridge send failure MUST be handled on both local Responses ingress and signed internal owner forwarding. Positive transport evidence that the current frame failed before dispatch MUST permit at most one reconnect and resend on the same account, within the existing request budget and before any response event. This retry MUST preserve the request's continuity anchor and account-scoped file ownership. A send whose dispatch is ambiguous MUST NOT be replayed. Exhausted or ambiguous send failures MUST return the established retryable HTTP 502 OpenAI error envelope with the transport's stable error code, settle API-key reservations before account-health writes, release pending and admission state, and settle the retry circuit through the existing failure lifecycle. Such failures MUST NOT escape as unhandled ASGI transport exceptions or be replaced by an owner-unreachable error when the owner returned a valid error response.

A reattach after a previous-response rejection MUST NOT publish a replacement socket still subject to an earlier connection's close lifecycle. Pending cleanup for the superseded socket MUST NOT close the replacement socket.

A local closed-before-dispatch refusal MUST NOT penalize the selected account. A prewarm send failure that precedes visible-request dispatch MUST complete prewarm cleanup and preserve the same retryable visible-request error contract.

#### Scenario: A native socket is closed before the frame is dispatched

- **GIVEN** a bridge request's native upstream socket is already closed before its send command is dispatched
- **WHEN** the bridge submits the request
- **THEN** it reconnects to the same account and resends the unchanged continuation once
- **AND** a successful resend retains pending ownership until its terminal response

#### Scenario: The replacement socket is also closed

- **GIVEN** the bridge has used its one pre-dispatch reconnect
- **WHEN** the replacement send also fails before dispatch
- **THEN** the bridge returns HTTP 502 with the stable transport error code
- **AND** the request's reservation, pending state, admission gate and retry-circuit ownership are settled
- **AND** no additional resend occurs

#### Scenario: Native command dispatch has an ambiguous outcome

- **WHEN** a bridge send fails after its command may have been dispatched
- **THEN** the bridge does not reconnect and resend that frame
- **AND** it returns the retryable error envelope and finalizes the request exactly once

#### Scenario: Owner forwarding preserves a bridge send failure

- **WHEN** a signed internal owner request encounters an exhausted or ambiguous send failure
- **THEN** the owner returns the same retryable error envelope as local ingress
- **AND** forwarding preserves that error without replacing it with `bridge_owner_unreachable`

#### Scenario: Headers committed before the submit failure

- **GIVEN** an HTTP bridge stream has already committed HTTP 200 before submission fails
- **WHEN** a send failure is finalized on local or signed internal owner ingress
- **THEN** the stream emits one `response.failed` terminal with the stable transport error code
- **AND** the native HTTP response policy does not convert that terminal into an ASGI exception

#### Scenario: Stale-anchor reattach overlaps old socket cleanup

- **GIVEN** an upstream previous-response rejection requires a bridge reattach
- **WHEN** old connection cleanup overlaps replacement selection or publication
- **THEN** cleanup cannot close the replacement socket or publish a closed replacement as usable

## MODIFIED Requirements

### Requirement: Native Codex preserves upstream failure lifecycle

For a native Codex HTTP/SSE Responses request, an upstream transport timeout or
stream EOF without a terminal Responses event MUST terminate the downstream
stream without synthesizing `response.failed`, `error`, or `[DONE]`. The proxy
MUST still execute reservation, request-log, account-health, and owned-resource
cleanup before propagating the termination. Non-native and OpenAI-compatible
clients MUST retain the existing stable terminal-error shaping.

An HTTP bridge submit send failure carrying explicit handled-send provenance
MUST instead follow the retryable error-envelope and terminal-event contract
in "HTTP bridge closed-socket sends preserve dispatch safety and terminal errors".
The same exception MUST apply when the error arrives through signed owner forwarding.

#### Scenario: Native Codex sees a truncated SSE lifecycle

- **GIVEN** a native Codex HTTP request has received a non-terminal SSE event
- **WHEN** upstream closes without a terminal event
- **THEN** downstream closes without a synthetic terminal event or `[DONE]`
- **AND** proxy cleanup and failure accounting still complete

#### Scenario: Non-native client keeps the terminal umbrella

- **GIVEN** an OpenAI SDK or other non-native client receives the same upstream
  truncation
- **WHEN** codex-lb normalizes the stream
- **THEN** the client receives the existing terminal `response.failed` shape

#### Scenario: Handled bridge send failure preserves its retryable envelope

- **WHEN** a native Codex HTTP request encounters an explicitly classified bridge submit send failure
- **THEN** it receives the established retryable HTTP error or an already-committed terminal event
- **AND** the native response policy does not raise that handled failure into ASGI
