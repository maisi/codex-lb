## Context
The deployed a08a0bf4 source and current upstream use raw `original_affinity_key`. Upstream issue Soju06/codex-lb#2655 is open; no matching merged fix was found. Internal keys from affinity.py deliberately retain LF. Removing it changes HMAC/session identity and collapses the header-unreachable namespace.

## Decisions
Use `x-codex-bridge-affinity-key-b64` exclusively for keys requiring encoding, not a `b64:` value prefix. The raw header remains literal, including `b64:...`. Both headers together are invalid. Base64URL uses UTF-8, padding, strict validation and canonical re-encoding. No stripping of encoded values or decoded identity. The only newly admitted illegal logical header character is the generated namespace's leading LF; all remaining characters and all other context fields retain existing checks. Whitespace-edge keys also use encoding to avoid identity loss.

The existing full-context tools-bound signature authenticates the decoded key and exact body in either primary signature version. Encoded requests never fall back to the ambiguous legacy primary signature. Raw legacy requests retain their current signature behavior. This avoids delimiter attacks and additive-header downgrade for the new format without changing existing signatures.

A small dependency-free codec is shared by parse_forwarded_request and the session-key fallback, avoiding the existing forwarding-to-helpers import cycle. Typed authenticated keys are already decoded and MUST NOT be decoded twice.

## Constraints and failure modes
New sender to old receiver with encoded keys fails signature verification (no raw key is emitted), rather than accepting a changed identity. Upgrade receivers before relying on encoded-key forwards; no claim of transparent mixed-version success. Public paths ignore all bridge-affinity headers, internal headers are stripped before upstream forwarding, and encoder prefix recognition grants no routing capability.

## Example
A key `\ncodex-lb-affinity-v1:thread_header:...` is sent as canonical Base64URL in the new header and restored with its LF before signature verification. A raw key `b64:c2lk` remains exactly that literal string.
