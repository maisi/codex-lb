## Purpose and evidence

The 2026-10-28 production report identified request
resp_070851d9920e863d016ae1f8cd37748191af353df8057836b4 at 14:30:05 Europe/Berlin.
Its matching proxy trace b897a7fa-4b46-4470-b1f6-4aebdaf2ba2f showed both Plus
accounts at 100% in both windows and a move to the preserve tier. Nearby traces
showed normal percentages again. The response ID itself was not in Loki; the
operator supplied the timestamp for correlation.

## Cause and decision

For a Plus secondary capacity of 7560 credits, dividing 160000 reserved tokens
by that capacity yields over 2100 percentage points before clipping. Adding
this to both observed windows makes ordinary concurrency look exhausted.
The correction leaves quota untouched and discounts weighted draws by local
load. Tokens are normalized per million solely for the load heuristic.

## Example

An account observed at 8% used in 5h and 15% used in 7d stays at those values
while one stream reserves 160000 tokens. At default weights its draw multiplier
is divided by 1.185. Releasing the lease restores its prior weight. The account
cards show the complementary 92% and 85% remaining, potentially from a newer
usage observation than an older request trace.

## Constraints and rollout

Quota caps, explicit upstream blocks, health tiers, additional quotas, sticky
ownership, and lease settlement retain their existing responsibilities. A
weekly-only account keeps primary usage null. No production configuration is
changed as part of this local fix. Operators who customized token pressure
should assess the corrected per-million-token unit after rollout.
