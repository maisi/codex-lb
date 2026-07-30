## Context

`RecentRequestsTable` renders thirteen header/body cell pairs directly and uses `table-fixed` without a minimum width. Account, API key, and model values are truncated as the viewport narrows. Reasoning effort is available on every request row but appears only as part of the model label, where it can be cut off. Dashboard preferences already use a Zustand store initialized at application startup and persisted in browser-local storage.

## Goals / Non-Goals

**Goals:**

- Let operators choose the request-log columns that matter on the current device.
- Make reasoning effort independently visible without changing the request-log API.
- Restore a validated device-local selection on later visits.
- Keep selected columns readable through explicit widths and horizontal overflow.

**Non-Goals:**

- Synchronize preferences between browsers or devices.
- Reorder, resize, sort, or filter columns.
- Change request-log data collection, API schemas, pagination, or details-dialog content.

## Decisions

1. **Persist column IDs in the existing dashboard preference store.** A versioned local-storage key stores only an ordered string array. Initialization accepts only known IDs, removes duplicates, and falls back to the current table columns when storage is missing, malformed, or contains no valid IDs. This keeps the preference device-local and avoids a server setting or new persistence abstraction.
2. **Keep the existing columns as the first-load default.** Reasoning effort is offered as a dedicated opt-in column. This preserves the current information layout for existing operators while making the requested transport-for-effort trade one interaction away.
3. **Render headers and cells from the same visibility predicate.** The table retains its current direct rendering and row behavior; each matching header/cell pair is guarded by the same typed column ID. A larger generic table framework is unnecessary for visibility alone.
4. **Prevent an empty table.** The chooser disables removal of the last selected column. A reset action restores the default selection.
5. **Derive a minimum table width from selected columns.** Each column has a stable width budget. The table remains at least container width and horizontally scrolls when selected columns need more room, rather than compressing all values until they truncate.

## Risks / Trade-offs

- Preferences are intentionally not shared between browsers; this is what allows phone and desktop layouts to differ.
- Adding future columns requires adding a typed ID, label, width, and matching cells. Unknown IDs from future or stale storage are ignored safely.
- The default still contains many columns and may scroll on small screens until the operator customizes it.
