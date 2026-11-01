# Implementation verification

The candidate is an unstaged working-tree change on approved base `ce414061cd4703dcf1a2327cc559cc62c7e2cfef`. This is implementation verification, not an independent review or a merge-readiness assertion. Parent owns independent review and publication.

| Dimension | Result |
| --- | --- |
| Completeness | All 11 tasks implemented or exercised; archive remains conditional and is held; freeze receipt covers final evidence creation. |
| Correctness | All 6 added requirements have implementation and scenario evidence; the final node acceptance batch passed 59 tests. |
| Coherence | One nullable persisted field, existing T1 identity, no routing/usage policy changes, no new setting/index/navigation/dependency, and immutable Oracle baseline. |

## Requirement and scenario mapping

- **Persisted execution identity / safe explicit labels:** Settings.processing_node, RequestLog.processing_node, repository insert, RequestLogEntry and mapper. Real Request API tests prove stored `home-b` and null survive reading on `reader-fixture`. HTTP streaming/nonstreaming routes prove explicit, unset, IP/domain-unsafe and spoofed-header cases. Boundary/env/hostname/credential-prefix cases are covered by test_request_processing_node.py.
- **Bridge ownership:** signed internal owner routes persist `instance-a` despite origin `instance-b`, for both upstream success and error. Ambiguous dispatch produces an ingress failure with null; a failed pre-dispatch handoff that recovers locally produces only a local execution row. Direct downstream WebSockets execute locally and preserve real API-key reservation finalization. The writer inventory and transport distinction are in context.md.
- **Additive schema and history:** the new default revision adds nullable VARCHAR(64) without defaults, index or backfill. Upgrade, new rows, historical nulls, parent-ledger replay over an existing compatible column, downgrade and re-upgrade pass. The actual startup regression for model-created schema was captured RED and fixed with the established existing-column guard. CLI upgrade/check report head, migration_policy=ok and schema_drift=none.
- **Oracle:** a separate restart-aware revision adds VARCHAR2(64 BYTE); incompatible surviving columns fail closed. The frozen baseline is unchanged; read-only head/transfer expectations match current metadata. The native Alembic ledger bound was tested RED (43 > 32) before shortening the descendant ID to `20261101_000100_request_node` (28 characters). Offline migration/model tests and transfer of non-null `home-b` pass. Live acceptance is not claimed.
- **Dashboard:** the real RecentRequestsTable and Zod parser cover owner/null/missing field in row and opened details. English/Korean/Chinese use localized fallback. Browser captures use labelled synthetic records and fixed time; the refined before capture renders exported base product source and the after capture asserts visible owner/Unknown labels.

## Evidence and limits

Evidence files live in the writer bundle identified by the final German report and writer-tests.json. Key results: writer-r103-node-acceptance (59 passed), writer-r72-final-unit-slice (1261 passed), writer-r55-writer-units (107 passed), writer-r79-migrations-final (50 passed / 9 PostgreSQL-only skipped), writer-r86-oracle-ledger-green (37 passed / 17 live cases skipped), and writer-r80-oracle-transfer-node (non-null provenance preserved).

Backend lint/format, architecture, cancellation, timing, settings tiers, migration topology, ty, frontend lint/type/build and strict change validation pass. Normal whole-spec validation passes 68 specs. Whole-tree strict validation has exactly the same 619 WARNING findings as the approved base, with no ERROR or added finding.

The full frontend run remains non-green (1699 passed / 9 failed). Stable API/settings failures reproduce on the approved base; both Dashboard timeout cases pass unchanged in isolated candidate follow-ups. The broad backend run remains non-green (672 passed / 3 failed): the retry fixture/assertion was corrected and passes; owner refusal passes unchanged in isolated base and candidate; the idle-recovery case reaches the same diagnostic 45-second timeout on both. Full unit execution was interrupted and is not represented as a pass. The existing git-vs-disk graph unit test cannot equate committed HEAD with the intentionally uncommitted new revision; the actual single-head fitness checker passes without changing that guard.

Because these wider gates are not all green and external database acceptance is forbidden in this task, this change is not archived. No test assertion, production guard or existing frontend deadline was relaxed to hide an inherited failure. No independent Codex review was launched; parent reviews the frozen candidate.
