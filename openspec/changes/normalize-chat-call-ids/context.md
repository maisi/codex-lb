# Context

This is an owned OpenAI-boundary mitigation, not a fix for the underlying hidden LiteLLM fallback. Opaque Gemini thought/signature IDs must remain intact on their original route. Only fresh Chat-derived function items are normalized; native Responses ownership is unchanged.

Use SHA-256 over the complete UTF-8 identifier, not the prefix before `__thought__`. Reserve short IDs from the entire converted request first. Deterministic numeric suffixes resolve even forced digest collisions without retrying the hash indefinitely. No global mapping is retained.

Example: a 166-character `call_…__thought__…` ID and its output share one compact surrogate; a second ID differing only in the suffix receives another. Arguments, outputs and original history remain unchanged. This does not establish successful live provider fallback or authorize deployment.

JSON-escaped unpaired surrogates can pass Chat request validation but cannot be UTF-8 hashed. Catch only that encoding error for oversized Chat-derived IDs and raise `ClientPayloadError(param="messages")`. The Chat route then returns HTTP 400 with the existing OpenAI `invalid_request_error` envelope (`Invalid request payload`) before dispatch, including when streaming is requested. Do not repair/strip the identifier, change short-ID behavior, or validate/rewrite native Responses input. Valid scalar Unicode still hashes the complete UTF-8 ID and preserves paired links. V1 Responses and compact converters already wrap `ValueError` subclasses; the confirmed HTTP 500 regression concerns the Chat route, not those wrappers.
