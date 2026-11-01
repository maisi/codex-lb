# Normalize Chat-derived call identifiers

## Why

Opaque provider tool-call identifiers can exceed the Responses 64-character limit after a hidden provider fallback. The owned Chat-to-Responses boundary currently copies these identifiers verbatim.

## What Changes

- Normalize only newly constructed Chat-derived function call/output identifiers in the shared message coercer.
- Preserve short IDs, complete-ID identity, pairing, source history and native Responses ownership.
- Cover real Pydantic mapping and mocked streaming/non-streaming API forwarding.
- Reject oversized Chat-derived identifiers that cannot be encoded as UTF-8 with a client payload error at the hashing boundary; Chat HTTP requests return 400 `invalid_request_error` with `param=messages` before upstream dispatch. Preserve valid Unicode mapping, short-ID behavior and native Responses ownership.

## Impact

- Affects Chat message coercion, including V1 Responses/compact `messages` compatibility.
- No dependencies, settings, routing, security, account or settlement changes.
- Does not repair LiteLLM fallback behavior or rewrite the original Gemini route.
