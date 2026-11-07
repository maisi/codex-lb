## 1. Release guardian connections

- [x] 1.1 Reuse per-operation accounts repositories for guardian reads and owned refresh; verify slow OAuth and peer-claim waits return all connections in a four-slot pool.
- [x] 1.2 Verify cancellation, partial refresh failure, successful token persistence, claim release, and session cleanup through the production guardian path.

## 2. Protect Oracle leader coordination

- [x] 2.1 Initialize and dispose a fixed Oracle leader pool and route every lease operation through it; verify lease progress with all background connections checked out and preserve other backends' behavior.
- [x] 2.2 Include the fixed slot in budget validation, CLI output, docs/context, and HA acceptance probes; verify 18/27/3 capacity arithmetic and rejection when no reserve remains.

## 3. Validate and finalize

- [x] 3.1 Run affected tests, make lint, uv run --extra oracle ty check, and strict OpenSpec validation; record results and live-Oracle limitations.
- [x] 3.2 Verify requirement/scenario coverage, sync stable specs/context, archive only after verification, and commit on the current branch with the requested trailer.
