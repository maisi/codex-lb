## Why
Generated Codex thread affinity keys intentionally start with LF to separate them from public header values. Owner forwarding currently treats that logical key as an HTTP header, rejecting every such cross-replica forward. The receiver also strips the LF and changes the signed identity.

## What Changes
- Transport generated internal affinity keys losslessly in a distinct canonical Base64URL header; leave safe legacy keys, including literal `b64:` strings, unchanged.
- Decode at both receive consumers before HMAC verification/session reconstruction, and reject ambiguous/malformed encodings without fallback.
- Preserve unsafe metadata rejection and public-header isolation. Encoded forwards require the existing full-context signature.

## Capabilities
### Modified Capabilities
- `sticky-session-operations`: safe lossless owner-forward affinity transport.

## Impact
Only bridge metadata transport, consumers, and regression tests. No settings, database changes, external inference, deployment, or publishing. Old receivers cannot handle encoded keys and must fail closed during a mixed-version rollout; existing safe-key forwarding remains compatible.
