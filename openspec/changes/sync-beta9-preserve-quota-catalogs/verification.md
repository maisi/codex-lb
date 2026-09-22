# Verification: beta9 integration and quota-catalog retention

## Summary

| Dimension | Status |
| --- | --- |
| Completeness | 7/9 implementation and evidence tasks complete; final verification and archive remain pending; release execution is tracked in PR #35 |
| Correctness | 2/2 delta requirements have implementation evidence; focused regression coverage exercises the principal migration, retention, and public continuation paths |
| Coherence | Implementation follows the design: operation-free migration convergence, separate fetch and retention sets, same-plan provenance, and existing snapshot persistence |

## Completeness

Tasks 1.1–1.2, 2.1–2.3, 3.2, and 3.4 are complete in
[tasks.md](tasks.md). Task 3.1 remains open for the final integration matrix
and corrections to imported OpenSpec deltas and the Rust dependency audit.
Task 3.3 remains open for archive after verification. External merge, image
publication, and deployed-health checks remain gated separately in PR #35.

The dashboard comparison evidence required by task 3.2 is stored in
[`evidence/`](evidence/), including before/after captures for the Accounts and
Settings surfaces. No new environment or dashboard setting was introduced by
the quota-catalog fix.

## Correctness evidence

### Beta9 migration convergence

- `app/db/alembic/versions/20260922_000000_merge_upstream_beta9_and_fork.py:11-29`
  declares the deployed beta6 and imported beta9 heads as parents and leaves
  upgrade/downgrade schema-neutral.
- `tests/integration/test_upstream_fork_migration.py:33-89` upgrades populated
  fork lineage and checks credentials, API-key priority, forced usage,
  continuation, and the single merge head.
- `tests/integration/test_upstream_fork_migration.py:92-114` upgrades a
  populated upstream beta9 database and preserves its authentication rows.
- `tests/integration/test_upstream_fork_migration.py:118-243` checks the
  populated downgrade/upgrade round trip and exact one-head topology.

### Temporary quota and rate-limit retention

- `app/core/openai/model_refresh_scheduler.py:116-177,251-260` excludes
  capacity-limited accounts from upstream fetch while passing their unchanged
  plan identities to registry reconciliation.
- `app/core/openai/model_registry.py:730-893` retains only same-plan,
  previously attributed model and service-tier evidence, preserves unknown
  accounts as unknown, and drops stale evidence when the account or plan no
  longer proves it.
- `tests/unit/test_model_registry.py:719-783` covers retention of a
  quota-limited account's model and tier and removal on plan change.
- `tests/unit/test_model_refresh_scheduler.py:616-666` covers the all-accounts
  capacity-limited refresh path for both rate-limit and quota-exhausted states.
- `tests/integration/test_http_responses_bridge.py:19111-19177` exercises both
  `/backend-api/codex/responses` and `/v1/responses`: the required owner stays
  recognized as model-capable, remains owner-bound, and returns the explicit
  owner-unavailable response instead of a model-policy conflict.

Local checks passed: 81 focused catalog/migration/bridge tests, 39 public
route/auth tests, 26 migration-topology tests, 57 simulation/options tests,
27 end-to-end tests, and all 1,600 frontend tests with coverage. Frontend lint,
TypeScript, build, eight browser smoke tests, Python lint/type/architecture
checks, packaging, and wheel assets passed. OpenSpec 1.11.0 validates the
change and all 65 main specs strictly.

Replacing only the scheduler with the deployed implementation makes the new
real HTTP bridge regression fail with the incident's exact `503
continuity_owner_policy_conflict`; both canonical and v1 paths pass with the fix.

The initial GitHub run passed 10,516 unit/simulation tests, all three core
integration shards, the full bridge suite, both SQLite and PostgreSQL migration
checks, Docker/Trivy, Helm lint and install smoke, and Nix. The local expanded
integration rerun was stopped after 1,263 passes and 21 skips when the equivalent
cloud matrix became available; it is not recorded as a full-suite pass.

## Coherence review

The implementation matches the design decisions and the stable specifications:

- runtime retention is a registry interpretation of temporary capacity, so no
  migration, setting, or routing bypass was added;
- account-specific provenance and plan equality prevent sibling-account
  inheritance and stale-plan relabeling;
- the beta9 migration adds a no-op convergence point instead of rewriting
  released revisions;
- request selection and hard continuity ownership continue to reject an
  exhausted owner even while its capability evidence is retained.

## Remaining warnings

1. The imported live-row facet delta now preserves its missing canonical
   scenario. Strict validation of every active changed folder and all 65 main
   specs passes locally; the next CI run must confirm it.
2. The imported Rust TLS dependency is updated for RUSTSEC-2026-0285. The native
   egress tests and dependency audit must confirm the patched dependency set.
3. PostgreSQL initially passed 237 tests and failed eight older-replica warmup
   fixtures because they omitted the fork's required transition key. The
   corrected fixture passes the SQLite selection (13 passed, eight PostgreSQL
   cases skipped); the PostgreSQL rerun remains required.

The initial macOS-only capture-tool guard failure is covered by the successful
Linux cloud unit suite. Local socket checks and post-commit topology tests also
passed. Final-head GitHub checks remain required before merge and deployment.
