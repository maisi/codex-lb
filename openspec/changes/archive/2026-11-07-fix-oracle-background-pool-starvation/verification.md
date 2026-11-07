# Verification: fix-oracle-background-pool-starvation

## Result

Implementation, requirements, and design agree. No unresolved implementation findings. The change adds no setting, migration, dependency, dashboard surface, or required setup step. Oracle request/background defaults remain 4/0; the fixed coordination slot is included in capacity accounting.

## Requirement and scenario evidence

| Contract | Implementation | Verification |
| --- | --- | --- |
| Guardian releases connections during slow work | `app/core/auth/guardian.py` reuses `BackgroundAccountsRepository` for outer reads and owned refresh; `TaskGroup` owns every worker | `test_auth_guardian_pool.py`: three slow OAuth/admission waits leave zero checkouts; renewal/background reads progress; cancellation plus one failed exchange preserves two rotations, paused status, and releases all claims; peer polling releases its reader and successfully adopts a peer rotation without OAuth |
| Independent Oracle leader capacity | `app/db/session.py` creates/disposes one fixed leader engine; all four lease-operation session sites in `leader_election.py` use its provider | `test_oracle_pool_isolation.py`: acquire, renew, release, reacquire, error cleanup, and disposal succeed with all eight general-purpose connections occupied; existing backend session tests prove no extra SQLite/PostgreSQL pool |
| Oracle budget includes coordination and overlap | `OracleSessionBudget` adds the shared fixed slot | CLI regressions assert 18 steady, 27 overlap, 3 reserve; seven-slot pools across two replicas reject the now-exhausted 30-slot budget |
| Oracle defaults and explicit overrides | Existing settings defaults/override validation remains unchanged; pool wiring adds only a fixed 1/0 engine | `test_settings_oracle.py`, `test_oracle_connection.py`, and bounded-pool startup integration test |
| Bounded real-process HA resource accounting | Existing HA worker holds request/background/leader pools concurrently and expects 18/27 total capacity | Updated Oracle HA acceptance probe; execution deferred because no running server/container may be touched |

The new regressions failed against the original implementation: concurrent guardian refreshes produced the same size-4/overflow-0 QueuePool timeout; peer polling retained connections; actual lease acquisition failed under background exhaustion. After releasing the retained read transactions, cancellation coverage exposed `gather` returning before sibling claim-release cleanup; the worker task group fixes that additional ownership failure.

## Commands and results

- `uv sync --frozen --extra oracle`: locked dependencies available.
- `make lint`: passed architecture, cancellation, timing-seam, settings-tier, migration-topology, Ruff lint, and formatting gates.
- `uv run --extra oracle ty check`: passed.
- Affected guardian/auth-manager/leader/session/settings/Oracle-budget/lifecycle/claim suites and integration paths: **334 passed, 17 skipped**. All live Oracle test URL variables and the external test-database URL were explicitly unset. One existing Starlette/AnyIO deprecation warning remains.
- Final six hermetic pool regressions after tightening adoption/shutdown assertions: **6 passed**.
- `npx --yes @fission-ai/openspec@1.11.0 validate fix-oracle-background-pool-starvation --strict`: passed.
- `npx --yes @fission-ai/openspec@1.11.0 validate --specs --strict`: **68 passed, 0 failed** after sync. All five delta requirement blocks match their main-spec counterparts.
- `git diff --check`: passed.

## Limits

No production service, running container, Oracle database, or other running server was accessed. The native Oracle lease-isolation regression and real-process HA probes are present but were skipped; native driver behavior and a fresh OCI/Autonomous HA acceptance run remain unverified. The reproduced lifecycle and guardian cadence explain the reported signature; exact production connection ownership during the observed UTC bursts was not directly measured. The independent pool protects checkout capacity, not database outages or a scheduler row held by another transaction.
