## ADDED Requirements

### Requirement: Bound Chat-derived function call identifiers

When converting Chat messages into Responses input, the service MUST preserve identifiers of at most 64 characters exactly and MUST map longer UTF-8-encodable identifiers to deterministic ASCII identifiers of at most 64 characters. Mapping MUST use the complete original identifier, MUST be request-local, and MUST preserve repeated call/output links without merging distinct identifiers, including digest collisions. All existing short identifiers in the request MUST be reserved before allocating replacements. Oversized Chat-derived identifiers that cannot be encoded as UTF-8 MUST raise a client payload error at the hashing boundary without stripping or repairing their contents; the Chat HTTP route MUST return HTTP 400 with an OpenAI `invalid_request_error` envelope and `param=messages` before upstream dispatch.

This requirement MUST also apply to the `messages` compatibility fields of V1 Responses and compact requests through the shared coercer. Native Responses `input`, including Responses-shaped Chat passthrough, MUST NOT be normalized. Source messages, arguments, results and opaque provider metadata MUST NOT be mutated.

#### Scenario: Opaque provider identifier exceeds the Responses limit

- **GIVEN** a Chat assistant tool call and matching tool result with the same 166-character opaque identifier
- **WHEN** the messages are converted and forwarded, in streaming or non-streaming mode
- **THEN** both items carry the same ASCII identifier of at most 64 characters
- **AND** source messages retain their original identifier

#### Scenario: Distinct full identifiers and collisions

- **GIVEN** long identifiers sharing a prefix but differing in their thought suffix, repeated links, and short identifiers matching candidate replacements
- **WHEN** the request is converted, even with colliding digests
- **THEN** distinct identifiers remain distinct and all short identifiers stay unchanged regardless of their position

#### Scenario: Oversized identifier contains an unpaired surrogate

- **GIVEN** a JSON-escaped unpaired high or low surrogate in an oversized assistant tool-call ID or any supported tool-output ID alias
- **WHEN** the Chat request is converted, in streaming or non-streaming mode
- **THEN** the service rejects it before upstream dispatch with HTTP 400 and an OpenAI `invalid_request_error` envelope with `param` set to `messages`
- **AND** the invalid identifier is not stripped or repaired

#### Scenario: Native Responses ownership

- **GIVEN** native Responses input containing a long opaque call identifier
- **WHEN** it passes through the Chat input compatibility path or either V1 request converter
- **THEN** the native input and its identifier remain unchanged
