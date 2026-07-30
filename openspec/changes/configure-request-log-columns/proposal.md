## Why

The Dashboard request-log table always renders every column into one fixed layout. Narrow screens compress useful values, and operators cannot trade low-value columns such as transport for fields such as reasoning effort. The preferred set also differs between a phone and a desktop.

## What Changes

- Add a Request Logs column chooser covering every table column and a dedicated reasoning-effort column.
- Persist the selected column IDs in browser-local storage so each device keeps its own layout without changing server-side settings.
- Validate persisted IDs, preserve a usable default for first load, and prevent a layout with no visible columns.
- Size the table from the selected columns so narrow layouts scroll instead of compressing selected values into unusable widths.
- Add frontend regression coverage for visibility changes, effort rendering, persistence, and invalid stored data.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `frontend-architecture`: Require configurable, device-local Request Logs column visibility.

## Impact

- Dashboard request table and preference store under `frontend/src/`.
- Dashboard translations and focused frontend tests.
- No backend API, database, navigation, dependency, or server-side setting changes.
