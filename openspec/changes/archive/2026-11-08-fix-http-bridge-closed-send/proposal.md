## Why

A production HTTP bridge continuation encountered a closed native upstream socket after stale-anchor recovery and its owner-forwarded request failed as owner-unreachable. Closed-socket sends need bounded recovery with explicit dispatch evidence and the same terminal settlement and HTTP error contract as other bridge send failures.

## What Changes

- Preserve positive pre-dispatch evidence from the native websocket adapter through bridge submission.
- Allow one same-owner reconnect and resend only when the failed frame was never dispatched; keep ambiguous sends fail-closed.
- Prevent stale-anchor reattach from handing a request a socket closed by an older lifecycle owner.
- Exercise actual bridge submission and signed internal owner forwarding with a closed native socket, including failure settlement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `responses-api-compat`: closed HTTP bridge sends use bounded, dispatch-aware recovery and preserve the retryable error envelope on local and forwarded routes.

## Impact

Native websocket error metadata, HTTP bridge submission and reconnect lifecycle, and bridge regression tests. No new configuration, migrations, external services, or user-facing features.
