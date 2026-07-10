## Why

`gpt-5.6-luna` can be advertised by an authenticated ChatGPT account yet fail through codex-lb because non-native requests omit the Codex `originator` and client `version` identity headers. The upstream routes that incomplete fingerprint to a rollout cohort whose Luna engine is unavailable, while the same account succeeds through the Codex CLI.

## What Changes

- Normalize non-native upstream Responses HTTP and websocket requests to the Codex CLI identity, including the `codex_cli_rs` originator and current Codex client version.
- Prevent inbound third-party originator and version values from overriding the normalized upstream identity.
- Cover the normalized identity contract on both HTTP and websocket upstream header builders.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `outbound-http-clients`: Non-native Responses traffic uses a complete Codex CLI identity when forwarded upstream.

## Impact

- `app/core/clients/proxy.py` outbound HTTP and websocket header construction.
- Unit coverage for proxy header normalization.
- ChatGPT Codex Responses routing for models gated by Codex client identity, including `gpt-5.6-luna`.
