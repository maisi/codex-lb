# Upstream beta5 integration verification

This merge imports upstream through `5794d8d7` and retains fork vending, ranked account selection, prompt-cache continuation, cache reports, targeted warmup and main-only Docker publishing. Issue #27 is handled separately.

The fork extracted account-state reconstruction before upstream changed it. Those upstream fixes now live in the extracted module; its health transition increments the generation once. The public selection facade forwards the dashboard snapshot into upstream selection. The settings ratchet includes the four existing fork vending topology/credential fields.

Migration tests upgrade populated databases from old and current upstream/fork heads, preserving API-key policy and account ranks. The new merge revision joins deployed histories without schema operations. Direct downgrade of the upstream merge retains the independent fork head.

Local evidence: 296 initial routing/settings tests; full unit run 8,985 passed with three failures subsequently fixed and all 1,383 proxy-utils tests passing; 322 HTTP/WebSocket bridge tests; 320 native transport tests; 27 end-to-end tests; 41 migration tests plus four corrected merge-branch cases. Type checking, lint, formatting and all 63 main OpenSpec validations passed. Frontend broad run had two locale-key parity failures (fixed) and two timing failures under host load; all 10 affected frontend tests passed on rerun. Final GitHub checks remain authoritative.

Settings screenshots captured from the actual beta4 fork and integrated beta5 source with the repository's seeded screenshot fixtures and Advanced settings expanded:

- [Before](../../../../docs/screenshots/beta5-settings-before.jpg)
- [After](../../../../docs/screenshots/beta5-settings-after.jpg)

For example, timeout and resilience tuning now appear in the dashboard while vending remains opt-in deployment topology. Imported upstream configuration keeps inherit precedence; fork account mappings and shared credentials are not dashboard behavior settings.

GitHub run `34327487742` verified all remaining integration-core shards, PostgreSQL tests and migration checks, browser smoke, packaging, Docker, Helm/kind and Nix. Its four substantive failures were the subsequently corrected locale parity, native-test harness, health-generation increment and retained-fork-head assertions. Each affected test suite passed locally after those corrections. This is implementation verification for archival; merge still waits for the actual final-head GitHub rollup.
