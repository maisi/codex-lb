# Chat Completions Compatibility Context

## Purpose and Scope

This capability aligns `POST /v1/chat/completions` with OpenAI’s expectations by mapping chat requests to Responses, preserving streaming behavior, and returning OpenAI-compatible error envelopes.

See `openspec/specs/chat-completions-compat/spec.md` for normative requirements.

## Rationale and Decisions

- **Mapping to Responses:** Chat Completions are derived from the Responses stream to keep behavior consistent across endpoints.
- **Responses-shaped passthrough:** Some OpenAI-compatible clients send `input` through `/v1/chat/completions`; those payloads are treated as Responses requests after chat-level validation.
- **Strict role/content rules:** System/developer messages are text-only; user content parts are validated for supported types.
- **Usage streaming:** When `stream_options.include_usage` is enabled, usage appears in the final chunk while earlier chunks include `usage: null`.
- **Obfuscation passthrough:** `stream_options.include_obfuscation` is forwarded to upstream when present.

## Constraints

- Oversized image data URLs (>8MB) are dropped from user inputs.
- Audio input (`input_audio`) is not supported and is rejected.
- Built-in Responses tools are preserved only on the Responses-shaped passthrough path; ordinary chat-message payloads keep the narrower chat tool policy.
- Omitted top-level `tools` stay omitted on the mapped Responses payload. `default_factory=list` plus an unconditional `to_responses_request()` write used to synthesize `"tools": []` and mark the field as set, which bypassed the Responses omit path (issue #1184). An explicit client-sent `[]` is still forwarded.
- `response_format` is translated to `text.format` with JSON schema validation.

## Failure Modes

- **Upstream stream failure:** Emit an error chunk, then terminate with `data: [DONE]`.
- **Non-stream failures:** Return an OpenAI error envelope. HTTP status follows
  the same map as non-stream `/v1/responses` (`429` for `rate_limit_exceeded`,
  not a blanket 502). The upstream Responses generator is closed so reservation
  finalizers run even when the first collected event is `response.failed`.
- **Invalid content types:** Reject with `invalid_request_error`.

## Examples

Streaming request with usage:

```json
{
  "model": "gpt-5.2",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": true,
  "stream_options": { "include_usage": true }
}
```

Responses-shaped chat request with a built-in tool:

```json
{
  "model": "gpt-5.2",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "Generate an image."}]}],
  "tools": [{"type": "image_generation"}],
  "tool_choice": {"type": "image_generation"}
}
```

## Operational Notes

- Streaming chunk mapping is validated in unit tests.
- Integration tests cover include_usage and tool call finish reasons.

## Chat-derived call identifier boundary

Chat `tool_calls[].id` values are provider-opaque. Hidden fallback can deliver a Gemini-style thought/signature identifier to a GPT Responses boundary where call IDs are limited to 64 characters. The shared Chat-message coercer therefore maps only overlong IDs on newly constructed function call/output items. It hashes the complete UTF-8 identifier and reserves every short ID in the request before allocating deterministic collision suffixes. Pairing and repeats share one request-local alias; source messages are not mutated.

This is deliberately not a global provider-signature rewrite. Native Responses `input` (including Responses-shaped input sent to the Chat route) remains owned by its caller and is passed through unchanged. The same coercion rule applies when V1 Responses or compact compatibility requests use their optional `messages` field. This boundary mitigation does not repair or claim to repair provider-aware fallback selection.

JSON escaping can carry an unpaired surrogate through Chat request validation. If an oversized ID cannot be encoded as UTF-8, the hashing boundary raises `ClientPayloadError(param="messages")` rather than stripping or repairing it. The Chat route returns HTTP 400 with the existing OpenAI `invalid_request_error` envelope and `Invalid request payload` message before upstream dispatch, for stream and non-stream requests. Valid scalar Unicode keeps the same complete-ID hash and paired alias. IDs of at most 64 characters bypass hashing unchanged; this does not add global Unicode validation or change native Responses input. For example, `"x" * 65 + "\ud800"` is rejected only when converted from Chat messages.
