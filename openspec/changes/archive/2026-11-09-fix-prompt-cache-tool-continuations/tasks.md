## 1. Continuation correctness

- [x] 1.1 Guard pending-call and tool-bearing suffix shapes; verify bridge completion-to-submit and wire-payload regressions.
- [x] 1.2 Retire missing-tool-output proxy anchors and reuse the bounded verified full resend before failure rewriting; verify successful recovery, client-anchor fail-closed behavior, unsafe/concurrent cases, repeated rejection, and file ownership.
- [x] 1.3 Verify a following submit cannot reuse the retired anchor after successful or failed fallback dispatch.

## 2. Validation and documentation

- [x] 2.1 Run affected bridge/continuation test modules, `make lint`, `uv run --extra oracle ty check`, and strict pinned OpenSpec validation; record results and any limitations.
- [x] 2.2 Verify requirements against code and tests, sync stable specs/context, and archive the verified change; record the verification report before archiving.
