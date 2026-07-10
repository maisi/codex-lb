## 1. Upstream Identity

- [x] 1.1 Normalize non-native Responses HTTP and websocket headers to the Codex CLI originator and cached client version.
- [x] 1.2 Record the stable non-native upstream identity contract in the outbound HTTP client context.

## 2. Regression Coverage

- [x] 2.1 Add HTTP header-builder coverage for replacement of third-party originator and version headers.
- [x] 2.2 Add websocket header-builder coverage for the same complete fingerprint and native-identity preservation.
- [x] 2.3 Verify routed HTTP and websocket upstream requests forward the complete normalized identity.

## 3. Validation

- [x] 3.1 Run focused proxy header tests and OpenSpec validation.
