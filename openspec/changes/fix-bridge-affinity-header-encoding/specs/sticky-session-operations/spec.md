## MODIFIED Requirements

### Requirement: Owner forwarding rejects illegal reconstructed header metadata
Owner-forwarded HTTP bridge requests MUST validate reconstructed bridge metadata before signing or posting. Wire metadata MUST NOT contain illegal HTTP header control characters. The generated `\ncodex-lb-affinity-v1:` logical affinity namespace MAY retain its single leading LF only through a canonical UTF-8 Base64URL encoded `x-codex-bridge-affinity-key-b64` header. All other illegal control characters in affinity, downstream turn-state, file-owner, client-IP, origin/target instance, or reservation metadata MUST fail closed with `bridge_forward_invalid`. Ordinary unsafe client headers MUST be omitted.

#### Scenario: Generated thread affinity crosses an owner hop
- **GIVEN** a generated thread selection key with the internal leading LF
- **WHEN** an origin builds an owner forward and the owner receives it
- **THEN** every receiver MUST restore the exact logical identity before signature verification or session reconstruction
- **AND** the wire headers MUST remain safe

#### Scenario: Unsafe reservation metadata fails closed
- **GIVEN** a reservation field contains an illegal HTTP control character
- **WHEN** the origin builds an owner forward
- **THEN** it MUST return `bridge_forward_invalid` without sending the owner request

#### Scenario: Unsafe client header is omitted
- **GIVEN** an ordinary client header contains an illegal HTTP control character
- **WHEN** the origin builds an owner forward
- **THEN** it MUST omit that header

## ADDED Requirements

### Requirement: Bridge affinity encoding preserves authenticated identity and legacy literals
Safe legacy keys MUST remain literal, including `b64:` values. Encoded forwards MUST use only the distinct encoded-key header with canonical Base64URL UTF-8 and MUST validate the existing full-context signature over the decoded key and posted body. Malformed, duplicate, ambiguous, noncanonical, tampered or downgraded encoded forwards MUST fail closed. Public requests MUST NOT gain internal affinity provenance through either header.

#### Scenario: Literal legacy prefix remains literal
- **GIVEN** a safe raw key `b64:c2lk`
- **WHEN** it is forwarded
- **THEN** its identity MUST remain `b64:c2lk` in both receive paths

#### Scenario: Encoded metadata cannot downgrade
- **GIVEN** a forward uses the encoded header
- **WHEN** the full-context signature is missing or invalid, or both affinity-key headers are present
- **THEN** the owner MUST reject it with `bridge_forward_invalid`

#### Scenario: Public encoded header is ignored
- **GIVEN** a public request supplies an encoded bridge affinity header
- **WHEN** its session key is reconstructed
- **THEN** that header MUST NOT select an internal affinity identity
