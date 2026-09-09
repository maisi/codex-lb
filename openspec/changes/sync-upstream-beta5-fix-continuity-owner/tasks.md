## 1. Upstream integration

- [ ] 1.1 Merge upstream `5794d8d7` and resolve conflicts while preserving fork-only behavior; verify no conflict markers.
- [ ] 1.2 Reconcile upstream migrations with the fork head and verify SQLite/PostgreSQL upgrade paths.

## 2. Continuity recovery

- [ ] 2.1 Implement account-neutral recovery from temporary soft-owner unavailability using existing replay projection and compare-and-set fencing.
- [ ] 2.2 Add public HTTP and WebSocket regression tests for successful recovery, unsafe replay and poisoned-anchor fencing.
- [ ] 2.3 Verify fork vending, account priority, prompt-cache continuation, warmup and reports remain intact.

## 3. Verification

- [ ] 3.1 Run focused, unit, integration, frontend, native, migration and OpenSpec checks.
- [ ] 3.2 Verify current-head GitHub gates and open a PR linked to issue #27 with `Fixes #27`.
