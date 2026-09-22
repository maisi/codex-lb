## 1. Prerelease integration

- [ ] 1.1 Merge upstream v1.25.0-beta.9 and reconcile conflicts while preserving fork capabilities.
- [ ] 1.2 Reconcile migration heads additively and verify populated fork/upstream upgrades.

## 2. Quota-safe model capability retention

- [ ] 2.1 Reproduce capability loss across temporary quota/rate-limit states.
- [ ] 2.2 Preserve valid last-known catalogs without bypassing quota or genuine policy removal.
- [ ] 2.3 Add public-path continuity, reset, removal, and persisted-snapshot regression coverage.

## 3. Verification and delivery

- [ ] 3.1 Run integration, unit, migration, frontend, packaging, lint, type, and strict OpenSpec checks; resolve regressions.
- [ ] 3.2 Record dashboard comparison and fork-capability verification evidence.
- [ ] 3.3 Verify implementation, sync stable specifications/context, and archive this change.
- [ ] 3.4 Publish the combined integration and fix, verify final-head GitHub gates, and update fork main.
