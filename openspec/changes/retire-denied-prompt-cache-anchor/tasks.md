## 1. Regression First

- [x] 1.1 Add a durable hermetic HTTP bridge regression adapted from the offline reproduction and verify it exercises real prompt-cache injection, denial handling, exact full replay, and the real next-submit dispatch for both retry outcomes and toggle-off controls.
- [x] 1.2 Add preservation and race assertions for newer sibling completion, unrelated alias, other-account continuity, file ownership, and denial publication versus final dispatch.
- [x] 1.3 Run the focused regression before production edits, verify the enabled cases fail for stale-anchor reuse while controls pass, and save the actual RED log under the supplied diagnostics directory.

## 2. Focused Fix

- [x] 2.1 Retire and fence the exact denied proxy-injected prompt-cache anchor before provenance mutation or fresh-replay early return, using the existing guarded lifecycle cleanup.
- [x] 2.2 Review the production diff and verify no retry eligibility, routing, ownership, downstream error, setting, schema, or unrelated behavior changed.

## 3. Verification

- [x] 3.1 Run the focused regression GREEN and save the actual log under diagnostics.
- [x] 3.2 Run the affected HTTP bridge suite and focused existing denial/prompt-cache controls with the required absolute interpreter, saving actual logs under diagnostics.
- [x] 3.3 Run focused lint plus strict OpenSpec validation and save actual logs under diagnostics.

## 4. Handoff

- [x] 4.1 Write `diagnostics/implementation-report.md` and a separate final summary artifact with scope, evidence, outcomes, and limitations.
- [x] 4.2 Review and stage only the exact implementation, regression, and OpenSpec changes; verify no commit, push, merge, deploy, original-checkout edit, production inference, or live database access occurred.
