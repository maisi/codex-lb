# Verification

## Completeness

All seven implementation/verification tasks are complete. Upstream ancestry is represented by merge commit f6aacf43. The follow-up reconciles fork-aware release admission and the settings-count baseline. All planned fork features retain their fields, API surfaces, implementation and regressions.

## Correctness

- Usage errors: upstream typed error parameters and nonterminal 404/402 classification pass their public proxy regressions; borrowed accounts remain excluded from background refresh and recover through successful vending.
- Migration compatibility: the new merge revision joins the deployed fork and upstream heads without editing existing revisions. Both parent upgrade tests preserve existing API-key flags and assignment ranks; PostgreSQL migration and schema checks pass.
- Release admission: subprocess tests exercise the actual guard CLI. Official upstream tag ancestry and matching versions are both required for import admission; missing provenance, unrelated ancestry, modified versions, non-fork events and authored release branches cannot use this path.
- UI: 1,267 frontend tests and five real-backend browser smoke tests pass. Synthetic before/after screenshots are included.

## Coherence

Upstream lifecycle implementations are preserved. The existing fork account-state extraction and service facade remain within architecture, cancellation and timing ratchets. Vending and continuation preserve explicit ownership constraints. Fingerprint and error-presence workarounds are consolidated on upstream equivalents.

## Remaining operational gates

Final-head GitHub checks and clean merge state must be verified before merge. Deployment, live account smoke and stable promotion are separate operational actions; the beta soak policy remains applicable. No known implementation findings remain after targeted correction tests.
