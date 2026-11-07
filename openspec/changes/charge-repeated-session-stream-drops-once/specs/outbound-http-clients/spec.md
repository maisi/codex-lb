## ADDED Requirements

### Requirement: Native websocket failures report a stable failure kind

When the native egress helper reports a websocket connect or post-connect
failure, its error event MUST include a `failure_kind` naming the failure class
from a fixed vocabulary (for example `reset_without_closing_handshake`,
`io_connection_reset`, `message_too_long` or `pong_timeout`). The kind MUST be
derived only from the error type, never from error text, peer data, headers or
URLs. The Python client MUST accept only lowercase identifiers matching
`[a-z][a-z0-9_]{0,63}` and MUST drop any other value. An accepted kind MUST
appear in the relay error message as `Upstream websocket <operation> failed
(<kind>)`. It MUST NOT change error codes, account-neutral classification or
replay eligibility.

#### Scenario: A reset without closing handshake is named

- **WHEN** the upstream websocket is reset without a closing handshake after a frame was sent
- **THEN** the relay error message ends with `(reset_without_closing_handshake)`
- **AND** the error code is the same as before this change

#### Scenario: An unexpected kind is not logged verbatim

- **WHEN** a helper event carries a `failure_kind` outside the accepted shape
- **THEN** the relay error message is `Upstream websocket receive failed` without a kind
