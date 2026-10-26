# HTTP connection lifecycle

The [connection-close requirement](spec.md#requirement-http-connection-close-tokens-are-case-insensitive)
covers transport completion as well as the response body. An HTTP 200 in an
application access log does not establish that a reverse proxy accepted a
healthcheck: connection-close framing can still be incomplete.

## Parser and response-cycle agreement

HTTP Connection tokens are case insensitive (RFC 9110 section 7.6.1).
Uvicorn 0.52.4's httptools response cycle recognizes an exact
`(b"connection", b"close")` request-header tuple. It misses `Close`, mixed
token lists and repeated fields even though httptools has already decided the
connection cannot persist. The parser can then stop accepting requests while
the response cycle leaves the transport open.

The adapter uses httptools' `should_keep_alive()` decision and adds the
canonical close field before creating the response cycle. It retains original
request headers and normal upgrade classification. Declining h2c keeps any
unrelated close token when the sanitized request is replayed. The h11 fallback
already implements the required close semantics.

## Example and operational check

An OCI-style readiness request sends:

```http
GET /health/ready HTTP/1.1
Host: backend:2455
Connection: Close
```

The result is the ordinary readiness JSON with `Connection: close`, followed by
TCP end-of-stream after the complete body. This does not change readiness checks
or bypass authentication. Ordinary persistent connections remain reusable.
For proxy health incidents, correlate the full response and connection shutdown
with the LB's health results; checking only status 200 can miss this defect.
