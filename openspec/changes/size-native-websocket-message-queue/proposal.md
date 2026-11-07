## Why

The native egress client fails a websocket when its per-connection message
queue overflows (`consumer_backpressure`), because the helper's single stdout
reader must never stall on one slow consumer. That queue held only 64
messages, while the HTTP/SSE queue is sized for 4096 events and 32 MiB so that
a healthy consumer that is merely late can absorb a burst of reasoning output.

Responses WebSockets carry the same events one frame per event. On 2026-11-07
the HTTP bridge lost one conversation's stream on every attempt after 40-80
events, on every account and on both replicas; after failure details were added
the drop was logged as `Upstream websocket receive failed (consumer_backpressure)`.

## What Changes

- Bound the native websocket message queue like the stream queue: 4096
  messages and 32 MiB of queued text and binary data, reusing the existing
  byte-budgeted queue.
- A consumer that stops draining still trips the bound and fails with
  `consumer_backpressure`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `outbound-http-clients`: Native websocket message buffering tolerates bursts.

## Impact

Native egress client and tests. No configuration, protocol or database change.
Worst-case buffered memory per stalled websocket rises to the same 32 MiB
already allowed per HTTP stream.
