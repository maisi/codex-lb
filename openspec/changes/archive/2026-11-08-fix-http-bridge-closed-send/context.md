## Scope and evidence

The 2026-11-07 incident involved `thread_header` affinity, native egress, and owner forwarding between oci-a and home-b. A stale previous-response rejection preceded reattach and a closed native send. No running service is used during investigation.

## Dispatch evidence

A local closed check before `_send_command` is positive evidence that this frame was never dispatched. A command acknowledgement timeout or a helper failure after command emission is ambiguous even when no response event arrived. Only the former permits the bounded same-account retry.

## Why the send handler did not prevent ASGI failure

The submit handler was reached and converted the native send error to a 502. The native HTTP response policy then recognized its general transport error code, re-raised the converted error inside the committed stream, and retained the original send traceback as its cause. The owner route applies that same policy to the forwarded native user agent. Explicit handled-send provenance now keeps these errors on the ordinary HTTP/SSE terminal path, including across the owner hop.

## Reattach ownership

Resource close awaits alias, lease and reader cleanup before reading the session's current socket. A concurrent reconnect could previously replace that socket during those awaits, allowing the old close owner to close the replacement. Reconnect now refuses a session with a resource-close owner both when claiming handoff and immediately before swapping the connection. A replacement opened during the race is closed by the failed handoff owner.

## Failure lifecycle

Submission owns queue registration, durable operation flags, admission, API-key reservation settlement and retry-circuit state. Retrying inside that ownership avoids duplicate operation registration. Ambiguous errors continue through the existing fail-closed contract.

Prewarm runs before ordinary visible-request queue publication and its send-failure handler. Its cleanup retains ownership of the warmup, while the submit boundary translates a remaining native transport exception into the same handled HTTP error for the still-undispatched visible request.

## Example

An anchored request with `previous_response_id=resp_previous` reaches an already-closed native socket. The first send emits no native command. The bridge reconnects to the same account and submits that same anchor once. If that send may have been dispatched before failing, the response is a retryable 502 and no third send occurs.
