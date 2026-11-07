## Context

See proposal.md for the incident. Settings._apply_oracle_pool_defaults selects 4/0 independently for each unspecified field, preserving explicit overrides. Request and background engines each apply those values. The defaults deliberately fit a 30-session Always Free budget with two replicas and one replacement.

Auth Guardian runs at startup after uniform 0–300-second jitter, then after each pass sleeps 21,600 seconds plus jitter. Its three workers currently retain eligibility-read sessions while AuthManager creates separately owned refresh sessions. Freshness reads in those refresh sessions autobegin read transactions that survive through claim polling and OAuth; claim/routing operations need yet more sessions. Four held readers can therefore block operations needed to release them. Three 30-second claim-release attempts can prolong a failure burst. The cadence matches production reports, but production traces and live Oracle are not available for direct attribution.

## Goals / Non-Goals

Release guardian connections around slow awaits and preserve existing rotation, claim, status, and cancellation fences. Protect Oracle lease operations from pool checkout contention. Keep the 4/0 configurable pools, other backends, and schema unchanged; no new knob or service operation is needed.

## Decisions

1. Reuse BackgroundAccountsRepository for the guardian's repository context. Each method already owns a short session and detaches returned rows before rollback, covering both the outer eligibility lookup and AuthManager's detached singleflight. Own workers with TaskGroup so cancellation or an early worker error cannot finish the pass before sibling refresh persistence and claim release drain; gather can propagate the first cancellation early. A larger pool would only postpone nested-session starvation. Changing the generic AuthManager transaction contract is unnecessary for this failing path.
2. Add one Oracle-only leader engine/session factory at background initialization and dispose it at database shutdown. All leader operations use a dedicated provider, which delegates to the existing background provider for other backends. One fixed slot is enough for short serialized operations; a separate configurable pool would add an unnecessary topology knob. Isolation protects checkout capacity, not database outages or lease-row locks.
3. Count the fixed slot centrally in OracleSessionBudget: per replica `2 * (size + overflow) + 1`. Share its fixed capacity with runtime construction. Defaults become 9 per replica, 18 steady, 27 at three-replica overlap, leaving three slots for the two-connection migration peak and administration. Update CLI diagnostics and existing real-process pool probes accordingly.
4. Exercise the production guardian builder/default repositories, AuthManager, real claim coordinator, and LeaderElection using local file-backed SQLite with a bounded async queue pool. Event barriers hold network work deterministically while assertions prove connection release and lease progress. Separately exhaust the entire background pool to prove the leader provider's isolation. Optional Oracle regressions are collected with live access disabled in this task.

## Risks / Trade-offs

- One additional Oracle session per replica reduces overlap reserve from six to three; preflight and deployment guidance include it. Explicit pool overrides still need an operator budget check.
- Native driver cancellation and real Oracle row locks require disposable Oracle acceptance; local SQLite proves lifecycle and pool contention but cannot establish those driver properties.
- Existing shielded refreshes intentionally finish after cancellation to preserve single-use token rotations; regression coverage must release controlled upstream waits and await task cleanup on failure.

## Migration Plan

No schema change. Deploy through the existing replacement procedure after checking `oracle-check --budget-only --replicas 2 --extra-replicas 1`. Rollback uses the previous code and previous eight-session-per-replica budget. This task performs no deployment.
