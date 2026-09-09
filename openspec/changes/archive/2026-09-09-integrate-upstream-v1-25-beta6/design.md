## Context

The verified beta5 integration ends at upstream `5794d8d7`. Twenty newer commits include beta6 and significant settings/report/native cleanup.

## Decisions

Preserve merge ancestry and resolve conflicts semantically. Adopt upstream replacements while retaining necessary fork deltas. Add a no-op merge revision for new upstream migrations; never reorder deployed fork history. Verify public bridge and native paths, account policies, reports and migrations, followed by final-head GitHub checks.

## Risks

Upstream report aggregation must not erase fork cache reporting. Removed settings may still have fork consumers and must be reconciled with the canonical constants or dashboard snapshot. Native event processing must retain fork completion fences.
