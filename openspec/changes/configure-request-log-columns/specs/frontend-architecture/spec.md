## ADDED Requirements

### Requirement: Request-log columns are configurable per device

The Dashboard Request Logs table SHALL expose an accessibly named chooser that lets an operator show or hide each table column, including a dedicated reasoning-effort column. The table MUST retain at least one visible column. The chooser SHALL expose an action that restores the default column set.

The selected column IDs MUST be persisted in browser-local storage and restored on later visits in the same browser. The preference MUST NOT require or write a server-side setting, so separate devices and browsers MAY retain different selections. Persisted data MUST be validated against known column IDs; malformed data or data with no known IDs MUST fall back to the default set.

Selected columns MUST retain stable readable width budgets. When their combined width exceeds the available viewport, the table MUST use horizontal overflow rather than compressing selected cells below those budgets.

#### Scenario: Operator replaces transport with reasoning effort

- **GIVEN** the Request Logs table is rendered with its default columns
- **WHEN** the operator hides Transport and shows Effort in the column chooser
- **THEN** Transport is absent from the table header and rows
- **AND** Effort is present as a dedicated header and each row shows its reasoning effort or an unavailable placeholder

#### Scenario: Selection is restored on the same device

- **GIVEN** an operator has selected a non-default request-log column set
- **WHEN** the Dashboard is opened again in the same browser
- **THEN** the table restores that selected set from browser-local storage
- **AND** no server-side preference request is required

#### Scenario: Different devices keep independent layouts

- **GIVEN** an operator uses separate browser-local storage on a phone and a desktop
- **WHEN** the operator chooses different request-log columns on each device
- **THEN** each device retains its own selection without overwriting the other device

#### Scenario: Invalid storage falls back safely

- **GIVEN** the persisted request-log column value is malformed or contains no known column IDs
- **WHEN** dashboard preferences initialize
- **THEN** the Request Logs table uses the default column set
- **AND** the invalid value does not prevent the Dashboard from rendering

#### Scenario: Selected columns remain readable on a narrow viewport

- **GIVEN** selected request-log columns require more width than the viewport provides
- **WHEN** the table renders on that viewport
- **THEN** the table exposes horizontal overflow
- **AND** it does not reduce the selected columns below their stable width budgets
