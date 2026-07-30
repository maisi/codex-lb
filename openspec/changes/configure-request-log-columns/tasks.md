## 1. Specification

- [x] 1.1 Define device-local request-log column selection, validation, and responsive readability requirements.

## 2. Preferences

- [x] 2.1 Add typed request-log column IDs and validated, versioned local-storage persistence to the dashboard preference store.
- [x] 2.2 Cover defaults, updates, restoration, and invalid persisted data in store tests.

## 3. Request Log Table

- [x] 3.1 Add an accessible column chooser with reset behavior and protection against hiding the final visible column.
- [x] 3.2 Render a dedicated reasoning-effort column and conditionally render every matching header/body cell.
- [x] 3.3 Derive table minimum width from visible columns so selected data scrolls rather than collapsing.
- [x] 3.4 Add localized labels for the chooser, reset action, and reasoning-effort column.

## 4. Verification

- [x] 4.1 Add focused component regressions for selecting columns, showing effort, and preserving a usable table.
- [x] 4.2 Run focused tests, frontend typecheck/lint, and available OpenSpec validation.
