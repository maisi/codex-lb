## 1. Prerelease integration

- [x] 1.1 Merge upstream v1.25.0-beta.9 and reconcile conflicts while preserving fork capabilities.
- [x] 1.2 Reconcile migration heads additively and verify populated fork/upstream upgrades.

## 2. Quota-safe model capability retention

- [x] 2.1 Reproduce capability loss across temporary quota/rate-limit states.
- [x] 2.2 Preserve valid last-known catalogs without bypassing quota or genuine policy removal.
- [x] 2.3 Add public-path continuity, reset, removal, and persisted-snapshot regression coverage.

## 3. Verification and delivery

- [ ] 3.1 Run integration, unit, migration, frontend, packaging, lint, type, and strict OpenSpec checks; resolve regressions.
- [x] 3.2 Record dashboard comparison and fork-capability verification evidence.
- [ ] 3.3 Verify implementation, sync stable specifications/context, and archive this change.
- [x] 3.4 Publish the combined integration/fix PR and record the final-head merge and image-delivery gates in its delivery checklist.

Release execution is tracked in [PR #35](https://github.com/maisi/codex-lb/pull/35):
all final-head GitHub checks must pass before updating fork main; image publication
and deployed revision/health are then verified. Archiving implementation artifacts
does not imply those external delivery steps have completed.
