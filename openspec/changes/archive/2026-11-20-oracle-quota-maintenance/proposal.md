## Why

The Oracle schema can exhaust its tablespace quota while expired bridge transcripts still occupy allocated extents. Usage history and request logging then stop advancing even while the dashboard remains reachable.

## What Changes

Show a dashboard warning when less than 3 GiB remains, offer operators manual online maintenance, and automatically attempt maintenance strictly below 2 GiB.

## Capabilities

### Modified Capabilities

- `oracle-database` gains quota monitoring and targeted bridge maintenance.

## Impact

Oracle deployments, dashboard runtime API and dashboard overview. Uses existing application grants and tables.
