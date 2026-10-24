# Verification: Oracle two-instance process failover

## Scope and evidence

The pilot uses real single-worker app processes, native Oracle connections and HAProxy 2.8.30. Upstream generation and OAuth are controlled wire endpoints; request routing, refresh claims, scheduler leader protection, bridge ownership and usage settlement are production paths. No production application change or schema migration was necessary for these accepted scenarios.

| Check | Result |
| --- | --- |
| Local Oracle Free 23 acceptance | 2 passed in 77.25 s |
| OCI Autonomous TP acceptance | 2 passed in 94.92 s |
| Native Oracle regressions excluding the opt-in HA target | 57 passed; the two unconfigured HA tests were skipped in this separate invocation |
| Focused SQLite/coordination regressions | 243 passed |
| Partial-startup and damaged-log child cleanup | 2 passed |
| Lint, format and architecture checks | Passed (`make lint`) |
| Whole-project type check | Passed (`ty check`) |

The separate full Oracle invocation still collected the explicitly named HA file despite `--ignore`; its absent HA URL accounts for those two skips. The delivered Makefile uses an explicit filtered target list and a separate signal-timeout HA invocation, avoiding both duplicate execution and the ordinary 300-second hard-exit watchdog.

| Measured interval / demand | Local Oracle | OCI TP |
| --- | --- | --- |
| Routing to survivor after SIGKILL | 1.29 s | 1.67 s |
| Scheduler takeover | 15.35 s | 15.18 s |
| Bridge ownership takeover | 29.51 s | 29.68 s |
| Simultaneous application slots, two processes | 16 | 16 |
| Simultaneous application slots, replacement overlap | 24 | 24 |

The test uses a 15-second scheduler lease; production still defaults to 60 seconds. Bridge recovery waits for the normal 30-second lease. Measurements are individual test observations, not service-level guarantees. The harness exercises the operator HAProxy example, changing addresses and adding observation plus the replacement backend.

## Requirement and scenario mapping

- Crash/retry and scheduler loss: `test_oracle_two_process_crash_retry_restart_and_drain` kills the leader after first stream output, verifies a truncated stream, survivor routing, one refresh exchange, singleton nonoverlap and exact completed usage accounting.
- Returning owner: the same scenario verifies peer forwarding on the same upstream WebSocket, takeover with a higher owner epoch and the original account pin, rejected stale renew/release/operation writes, and the restarted process forwarding to the successor without changing ownership.
- Drain/replacement: accepted held work completes and settles; readiness excludes the draining process; real pool barriers hold all 16/24 slots concurrently.
- Existing target: `test_oracle_ha_preserves_nonempty_target` preserves a sentinel row; startup refuses tables, views and sequences. Fixtures remove only application objects installed after their empty-target check.
- Process cleanup: `test_oracle_ha_lifecycle.py` verifies reaping after partial startup and even after an unreadable observation log.
- Support boundary: the operator guide, Oracle contract and replica context explicitly permit stream interruption and forbid claims of transparent continuation or exactly-once upstream execution. The continuation assessment cites current spool constraints and official public-API cursor documentation without assuming ChatGPT-backend support.

## Remaining delivery verification

Inspect the stacked PR's actual head, Oracle workflow and `CI Required` before marking cloud verification complete. PostgreSQL regression evidence comes from that CI job; no PostgreSQL application code changed. The dedicated local and OCI HA schemas must be confirmed empty after the successful runs. Specs/context are synchronized; archive only after the remaining checklist items are verified.
