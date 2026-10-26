# Verification

## Completeness and correctness

- Reproduced the failure before the fix through a real TCP request to the actual
  `/health/ready` route: `Connection: Close` receives complete 200/database-ok
  JSON, then times out waiting for EOF.
- After the six-line adapter change, 93 focused tests passed, including fourteen
  new real-socket readiness cases over httptools and h11. Cases cover lowercase,
  mixed/uppercase, token lists, repeated fields, reusable keep-alive and declined
  h2c offers. Existing WebSocket, upgrade-body delivery, disconnect-stamp,
  keep-alive timer, health and CLI cases also passed.
- Focused Ruff lint/format and ty checks passed. The change and owning main spec
  pass strict OpenSpec validation. Main and delta requirement content agree.
- `make lint` passed, including architecture/cancellation/timing/settings checks,
  migration topology against fetched current main, and full Ruff lint/format.
- The source on current GitHub main was checked before preparing the focused PR;
  the installed original production source matched the same original file hash.

## Production trial

On 2026-10-26, the original single protocol file was backed up privately and the
same tested source was copied into the existing Docker container. Its original
ownership/mode were restored. The container was restarted with its existing
image/configuration and SQLite volume. The bounded trial would restore the
original source if public recovery was not observed.

At 01:30:50 and 01:30:55 UTC both the public readiness URL and direct OCI origin
returned 200; local OCI-style probes received the complete 200 response plus EOF.
The dashboard root returned 200. Unauthenticated protected API routes returned
their expected 401, establishing routing to the application without making a
paid model call. Fresh captures show both OCI probe streams receiving an
immediate server FIN after the response, within tens of milliseconds.

No OCI policy, database backend, account data or image tag was changed. The
runtime source patch remains in place after recovery; image replacement will
discard it until the permanent fix is shipped. The trial backup/report are
local incident artifacts and are excluded from the PR.

## Coherence

The implementation follows the existing parser adapter, uses the parser's
decision and adds no settings or readiness bypass. Context explains the HTTP
contract and concrete probe example. The application change is separate from
the incident diagnostic collector work.
