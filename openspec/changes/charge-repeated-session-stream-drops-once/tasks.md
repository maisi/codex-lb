## 1. Diagnostics

- [x] 1.1 Emit a fixed-vocabulary `failure_kind` on native websocket error events
- [x] 1.2 Parse it defensively in the native egress client and append it to relay error messages
- [x] 1.3 Keep the kind visible in the bridge `reader_failure` log line
- [x] 1.4 Cover the mapping in Rust and the subprocess-to-relay path in Python

## 2. Account health

- [x] 2.1 Charge only the first mid-stream drop per bridge key within the window
- [x] 2.2 Log skipped penalties as `account_penalty_skipped`
- [x] 2.3 Regression test through the bridge relay path, including other keys and window expiry

## 3. Verification

- [x] 3.1 Rust tests, fmt and clippy for the egress and protocol crates
- [x] 3.2 Python lint, type check and affected test modules
- [x] 3.3 Strict OpenSpec validation
