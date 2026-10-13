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
