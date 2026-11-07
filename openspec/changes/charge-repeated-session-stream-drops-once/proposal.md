## Why

On 2026-11-07 one client conversation's HTTP bridge replay was cut off by the
upstream websocket after 40-80 response events on every attempt: on three
different accounts and on both bridge replicas, which egress through unrelated
networks. Each drop recorded a transient account error. Three drops cooled the
only routable account and the pool answered `503 no_accounts`, so a single
broken conversation took the service down for every caller. The hard-key retry
circuit did not intervene because the conversation used a soft prompt-cache key
and the drops happened after response events.

The logs could not explain the drops either. The native egress helper reduces
every post-connect websocket failure to "transport failed" or "protocol failed",
so a TCP reset, a reset without a closing handshake and an oversized frame all
logged as `Upstream websocket receive failed`.

## What Changes

- Within a 15-minute window, only the first mid-stream reader drop for an HTTP
  bridge key is charged to account health. Later drops for that key are logged
  as `account_penalty_skipped` and settle their requests without an account
  penalty. Eventless drops, close frames and other keys are unchanged.
- The native helper adds a credential-free `failure_kind` from a fixed
  vocabulary to websocket error events. Python accepts only that shape and
  appends it to the relay error message, and the bridge `reader_failure` log
  keeps it untruncated. Failures without a kind name their phase instead, so a
  local queue overflow appears as `consumer_backpressure`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: Repeated mid-stream drops for one bridge key charge
  account health at most once per window.
- `outbound-http-clients`: Native websocket failures report a stable failure
  kind.

## Impact

Native helper protocol (additive, optional field), native egress client, HTTP
bridge reader failure path and tests. No configuration, dependencies or database
migration. Not fixed here: the retry circuit still ignores soft keys and
post-output drops, so a client can keep retrying the broken conversation; it
now fails without cooling down the pool.
