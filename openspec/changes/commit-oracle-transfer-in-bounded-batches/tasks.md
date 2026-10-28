## 1. Bounded transfer

- [x] 1.1 Commit the incomplete-transfer marker after pristine/target checks and before any data batch; commit every seed-clearing, copy and self-reference batch separately.
- [x] 1.2 Restart a marked target by clearing it in committed batches while preserving the marker; keep rejecting unmarked used targets.
- [x] 1.3 Exclude the marker from per-table verification, remove it only after all tables verify, and report fenced failures and dry-run marker state.
- [x] 1.4 Refuse application startup on an Oracle database carrying the marker.

## 2. Verification

- [x] 2.1 Unit-test committed partial state, the startup fence, restart to an exact copy, dry-run reporting and the unchanged used-target rejection.
- [x] 2.2 Real-Oracle test: injected mid-transfer failure leaves a fenced target, rerun completes and removes the marker.
- [x] 2.3 Run focused tests, lint/types and strict OpenSpec validation; update runbook/context; record production re-run evidence in `verification.md`.
