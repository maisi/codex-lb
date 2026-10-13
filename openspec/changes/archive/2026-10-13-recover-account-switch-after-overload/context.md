# Incident and scope

On 2026-10-13 the beta.9 production instance emitted a native capacity 429 at 08:40:46 UTC, then 70 `previous_response_owner_unavailable` errors from 08:42:06 to 08:46:21. Two other accounts served requests in the same window. Rejected replay reasons included `prefix_fingerprint_mismatch` and `anchor_metadata_missing`; repeated client retries could not change either proof.

For example, a stored turn `[user: first question] -> [assistant: answer]` followed by an anchored delta `[user: second question]` can be rebuilt as all three messages and submitted without the previous account's response ID. This is allowed only while the new turn has not been dispatched and the complete conversation is portable.

The broader `relocate-anchored-turns-across-accounts` proposal also covers ambiguous accepted operations. That requires additional duplicate-dispatch fencing and is separate from this change. This change recovers definitive admission-time owner loss and recognizes the observed capacity message.

Monitor owner-backoff waits, durable-transcript relocation decisions and owner-unavailable errors after deployment. An incomplete transcript remains a refusal, not a reason to discard context. No account status or production database is edited by the implementation workflow.

## Implementation and verification (2026-10-13)

The implementation recognizes native capacity wording, bounds owner backoff
reads and waits by the original request deadline, and reconstructs only a
scoped, complete, settled transcript. Successful unanchored roots are captured
at completion through the existing optional spool; this preserves prior live
retry and ambiguous-dispatch behavior. Historical missing roots remain a
refusal. No production process, account status, or database was modified.

Verification results:

- 1930 unit tests passed across bridge, replay safety/transcript, durable ring,
  balancer, virtual-clock, concurrency, contract, and load-deadline/cancellation
  suites.
- All 231 existing HTTP bridge integration tests and 22 promotion/accounting
  tests passed. The 16 new owner-recovery route tests passed after correcting
  test clock/settings overlays and enabling API-key authentication in those
  fixtures. Combined coverage: 2199 distinct passing tests.
- Real route tests cover native capacity 429 retry, public/native delta
  relocation, subsequent replacement ownership, excluded-owner routing, quota
  catalog eligibility, distinct independent roots, file binding, single-account
  policy, foreign scope, orphan tools, incomplete/failed recording, connect
  failure, bounded waiting, original deadline, cancellation, released account
  capacity, API-key account restrictions, and reservation settlement.
- Repository-wide Ruff check/format, ty, proxy architecture, cancellation,
  timing seams, settings tiers, migration topology, and git whitespace checks
  passed. No migration was added.
- The change passes strict OpenSpec validation. Main-spec validation passes all
  67 specs. OpenSpec 1.14.1 additionally flags existing requirement descriptions
  over 500 characters in whole-repository strict mode (59 specs before sync);
  these are pre-existing style warnings, not new contract errors.

Verification mapping:

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Native capacity recovery | `helpers.py` classifier and existing HTTP capacity retry | Unit capacity variants and route lifecycle retry |
| Bounded owner wait | `_load_balancer/continuity_recovery.py`, HTTP `streaming.py` | Same-owner, deadline, cancellation and zero account-pressure route tests |
| Complete stored transcript relocation | `replay_transcript.py`, HTTP `transcript_recovery.py`, scoped repository reads | Wire, tool, corruption/bounds units; public/native relocation and scope/settlement routes |
| Client full-resend proof remains independent | Existing full-resend projection; stored proof as an additional lane | Existing full-resend and no-material refusal regression tests |

All seven tasks are complete; the four requirements and their scenarios are
implemented and covered. Design, implementation and main context agree. The
broader relocation change is untouched. Deployment remains separate.

## CI follow-up (2026-10-13)

The first GitHub run passed integration, migration, packaging, OpenSpec, lint,
and type checks. Its full unit job exposed three completed-delivery regressions:
the optional root-capture call read settings before rejecting sessions without
durable ownership metadata. Persistence now returns before root capture when
the durable session ID or owner epoch is missing. The existing three failing
stream-lifecycle tests reproduce the issue and pass after this correction;
all 1144 tests across cancel/drain, HTTP bridge, transcript recovery, and owner
recovery routes pass locally. Ruff, ty, architecture, cancellation, and
whitespace checks also pass.

The Docker image built successfully, but its Trivy gate separately rejected
the unchanged urllib3 2.7.0 dependency for CVE-2026-97687 and CVE-2026-97689.
The scan lists 2.8.0 as the fixed version. This dependency blocker is separate
from the proxy recovery correction.

The maintainer requested the dependency update in the fork. The urllib3
minimum is now 2.8.0, and the lockfile pins 2.8.0 with registry-provided artifact
hashes. Other dependency versions and the project version are unchanged.
Frozen installation, offline lock validation, package compatibility and
application imports pass. All 199 selected HTTP client, OAuth, tracing,
telemetry, release and cancel/drain tests pass with the existing database-reset
fixture and an isolated test data directory. The initial partial-suite run
lacked database tables for several lifespan tests; rerunning with that fixture
resolved those failures. Ruff and whitespace checks pass. The preceding cloud
run already confirms the completed-delivery unit correction; the updated image
still requires a fresh Trivy result.
