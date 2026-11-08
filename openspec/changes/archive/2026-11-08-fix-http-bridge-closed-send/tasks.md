## 1. Dispatch-aware send recovery

- [x] 1.1 Preserve positive native pre-dispatch rejection evidence and verify native websocket adapter regression coverage.
- [x] 1.2 Route closed-socket sends through one same-account retry and existing terminal settlement; verify bridge submit regressions for success, exhausted retry, ambiguous dispatch, and reservation/pending/circuit cleanup.
- [x] 1.3 Audit and fix stale-anchor reattach socket ownership at its source; verify the failing lifecycle interleaving with a deterministic regression.

## 2. Route validation and completion

- [x] 2.1 Verify local Responses and signed internal owner forwarding preserve send-failure envelopes without ASGI exceptions, using route regression tests and bridge-forwarding tests.
- [x] 2.2 Run `make lint`, `uv run --extra oracle ty check`, affected test modules, and strict OpenSpec validation; document results and limitations.
- [x] 2.3 Verify implementation against the change and sync stable spec/context before archive.
