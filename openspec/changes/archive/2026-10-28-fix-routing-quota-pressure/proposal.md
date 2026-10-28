## Why

Routing adds raw leased-token counts divided by subscription credits to both
quota percentages. A concurrent request can therefore turn available 5h and 7d
quota into 100% in the routing trace, trigger a false budget-tier fallback, and
send traffic to a preserve account instead of an available burn-first account.

## What Changes

- Keep normalized upstream quota percentages separate from replica-local load.
- Apply in-flight and leased-token pressure as a dimensionless discount to
  weighted selection, with leased tokens normalized per million tokens.
- Evaluate quota thresholds and record routing-trace quota values using actual
  normalized usage, independent of concurrent leases.
- Correct the existing settings explanation and cover routing, traces, and
  lease release through the proxy API.

## Capabilities

### Modified Capabilities

- `account-routing`: local load discounts draw weights instead of quota values.
- `proxy-runtime-observability`: routing-trace quota values exclude local load.
- `frontend-architecture`: quota help describes load weighting separately.

## Impact

No migration, new setting, or API field. Existing load knobs remain effective
for weighted selection. Budget tiers and sticky quota thresholds stop treating
local load as upstream quota consumption. The request-details layout stays
the same; its existing used-percent fields become stable quota observations.
