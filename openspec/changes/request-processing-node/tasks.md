# Tasks

## 1. Persisted Request API contract
- [x] 1.1 Demonstrate the missing processingNode field through the real Request API (record RED), add nullable model/repository/schema/mapping and safe local writer identity, and record GREEN.
- [x] 1.2 Prove raw HTTP streaming/nonstreaming success, error/retry and unset/unsafe/spoofed identity through persisted Request API records with synthetic upstreams.

## 2. Ownership and settlement
- [x] 2.1 Prove bridge owner, ingress failure, local recovery and direct WebSocket attribution with regression tests; preserve reservation settlement and routing.
- [x] 2.2 Trace every request-log write path, cover alternative writers and document the final topology in context.md.

## 3. Database evolution
- [x] 3.1 Add linear nullable migration; demonstrate upgrade/downgrade, historical null and new rows, single head and strict topology checks.
- [x] 3.2 Add Oracle descendant migration without changing the frozen baseline; verify offline schema, drift and transfer compatibility tests.

## 4. Dashboard
- [x] 4.1 Capture browser BEFORE from explicitly labelled synthetic fixtures with a fixed clock.
- [x] 4.2 Demonstrate component/schema RED for owner/unknown/missing field, implement compact list/detail i18n display, record GREEN and browser AFTER.

## 5. Integrated verification
- [x] 5.1 Run relevant HTTP/WS/bridge, Request API, migration, backend guard/lint/type and frontend lint/type/build/test suites through the isolation wrapper; retain full exit-coded logs.
- [x] 5.2 Sync stable specs/context, strict-validate OpenSpec, verify completed artifacts and archive only if verified.
- [x] 5.3 Write German report and exact test ledger; freeze all scoped candidate files including untracked artifacts/screenshots with SHA256, Git blobs and full diff.


## Verification disposition

Implementation and scoped acceptance are complete (59 final acceptance tests passed). The broad runs, baseline comparisons, exact commands, counts and limitations are retained in the writer evidence bundle. The freeze manifest is the completion receipt for task 5.3. No commit, push, PR, merge, deployment or external database operation is part of this change.

Archive is deliberately deferred: whole-tree strict OpenSpec validation has the same 619 pre-existing warnings as the approved base; the whole frontend/backend runs are not all green; native PostgreSQL/Oracle acceptance remains unavailable under the external-database restriction. The change stays active for the parent's independent review and native acceptance. No unverified change is archived.
