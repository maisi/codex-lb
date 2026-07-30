# Tasks: prompt-cache-affinity-continuation

## 1. OpenSpec
- [x] 1.1 Define API-key policy, verified continuation, observability, and dashboard requirements.
- [x] 1.2 Validate the change artifacts and main specs.

## 2. API-key policy
- [x] 2.1 Add the default-false database column and migration.
- [x] 2.2 Expose and persist the setting through API-key create/update/read/regenerate flows.
- [x] 2.3 Add dashboard create/edit controls and persistence tests.

## 3. Verified continuation
- [x] 3.1 Prepare prompt-cache continuation only from exact full-prefix and owner/model/account proof at serialized send ownership.
- [x] 3.2 Forward only suffix input and preserve full-resend fallback behavior.
- [x] 3.3 Record bounded attempt/success/skip/fallback outcomes and classify only proven turns as follow-up.
- [x] 3.4 Cover success, mismatch, unrelated payload, compaction, concurrency, ownership, and stale-anchor fallback.

## 4. Cache reports
- [x] 4.1 Add API-key report filters/grouping and canonical input/cached-input aggregation.
- [x] 4.2 Add cache summary definitions and daily subset trends to the Reports UI.
- [x] 4.3 Cover calculations, filters, grouping, and rendering.

## 5. Verification
- [x] 5.1 Run focused backend migration, API-key, bridge, reports, lint, and type checks.
- [x] 5.2 Run focused frontend API-key and reports tests, lint, and type checks.
- [x] 5.3 Review the final diff and commit without pushing or deploying.
