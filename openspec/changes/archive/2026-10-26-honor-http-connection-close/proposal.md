## Why

OCI health requests send `Connection: Close`. The httptools server responds 200
but leaves the connection open because Uvicorn recognizes only an exact lowercase
header tuple. The parser itself marks the connection closed and ignores a second
request. This reproducible defect is a candidate cause of failed LB healthchecks.

## What Changes

- Respect the HTTP parser's connection-close decision and expose the canonical
  close header to Uvicorn's response cycle.
- Verify mixed-case, token-list and repeated Connection fields over real sockets
  using the readiness route, plus normal keep-alive and upgrade behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `http-ingress-limits`: Honor HTTP connection-close tokens case-insensitively.

## Impact

HTTP protocol adapter, integration tests and owning spec. No configuration,
dependencies or database migration. Production recovery must be checked separately.
