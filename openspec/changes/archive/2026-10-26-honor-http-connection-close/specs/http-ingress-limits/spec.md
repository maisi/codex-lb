## ADDED Requirements

### Requirement: HTTP connection-close tokens are case insensitive

For ordinary HTTP/1.1 responses, the server MUST honor the `close` Connection
token case-insensitively, including when it occurs in a comma-separated token
list or repeated Connection fields. It MUST send the complete response and close
the transport promptly after completion rather than waiting for the keep-alive
timeout. It MUST advertise `Connection: close` on that response. Requests that
permit persistence MUST retain normal keep-alive behavior. Both the httptools
protocol and h11 fallback MUST satisfy this contract.

#### Scenario: OCI readiness request asks for connection close

- **WHEN** a readiness request sends `Connection: Close`
- **THEN** the server sends the complete readiness response and `Connection: close`
- **AND** the client observes end-of-stream immediately after that response

#### Scenario: Equivalent Connection headers include close

- **WHEN** a request includes mixed-case close in a token list or repeated fields
- **THEN** the server sends the complete response and closes the connection

#### Scenario: Persistent readiness requests remain reusable

- **WHEN** a readiness request permits HTTP/1.1 persistence
- **THEN** a subsequent request on that connection is served normally

#### Scenario: A declined protocol offer retains a close token

- **WHEN** a request offers h2c with a mixed-case close Connection token
- **THEN** the server serves the complete plain HTTP response and closes the connection
