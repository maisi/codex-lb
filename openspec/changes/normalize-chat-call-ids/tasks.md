## Implementation

- [x] Reproduce the 166-character ID failure through the real Pydantic forwarding chain before production edits.
- [x] Add minimal request-local normalization with short-ID reservation and collision disambiguation.
- [x] Verify boundaries, Unicode, full-ID identity, aliases, repeated links, source immutability and native ownership, including shared V1 callers.
- [x] Verify streaming and non-streaming Chat API forwarding with an upstream stub.
- [x] Sabotage normalization, observe regression failure, restore and run final affected suites and static/spec gates.
- [x] Synchronize SSOT, stage only scoped candidate files and preserve immutable evidence for independent acceptance.

## Oversized malformed-Unicode rejection

- [x] Reproduce HTTP 500 on the real Chat route using JSON-escaped unpaired surrogates before production edits; assert HTTP 400, the OpenAI envelope and no upstream dispatch.
- [x] Reject only unencodable oversized identifiers at the hashing boundary with `ClientPayloadError(param="messages")`; verify Pydantic callers, valid Unicode and pairing.
- [x] Rerun selected suites and static/spec gates, preserve failed-candidate evidence, and freeze only the scoped files for independent re-review.
